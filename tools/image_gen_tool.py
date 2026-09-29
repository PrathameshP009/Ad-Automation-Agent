"""Generates a cinematic still for each storyboard shot via NVIDIA-hosted FLUX.

Uses the same NVIDIA_API_KEY as the LLM. The endpoint is configurable (NVIDIA_IMAGE_URL in
.env) because NVIDIA's catalog changes over time; copy the exact invoke_url from the model's
"Build" tab on build.nvidia.com if the default stops working.

Any failure returns None, and the caller falls back to a placeholder card, so a bad image
call never breaks the whole render.
"""
import base64
import io
import time
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image

import config
from tools.llm_client import _log_error

STYLE_SUFFIX = (
    ", cinematic film still, dramatic lighting, shallow depth of field, anamorphic lens, "
    "rich color grading, ultra detailed, vertical 9:16 composition, no text, no watermark, no logos"
)

# FLUX on NVIDIA accepts a fixed set of dimensions; 768x1344 is the closest to 9:16.
GEN_WIDTH, GEN_HEIGHT = 768, 1344
TARGET_WIDTH, TARGET_HEIGHT = 1080, 1920

REQUEST_TIMEOUT = 90          # seconds per image request
MAX_CONSECUTIVE_FAILURES = 2  # after this many failures in a row, stop trying for this run
_consecutive_failures = 0
_last_pollinations_call = 0.0
POLLINATIONS_MIN_INTERVAL = 16  # anonymous tier allows roughly 1 request / 15s


def generate_still(prompt: str, out_path: Path, seed: int = 0) -> Path | None:
    """Circuit breaker: if the image endpoint keeps failing, skip it for the rest of the run
    instead of burning minutes of timeouts on every remaining shot."""
    global _consecutive_failures
    if not config.NVIDIA_API_KEY or _consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        return None
    result = _try_generate(prompt, out_path, seed)
    _consecutive_failures = 0 if result is not None else _consecutive_failures + 1
    if _consecutive_failures == MAX_CONSECUTIVE_FAILURES:
        print("[image_gen] Too many consecutive failures; using placeholder cards for remaining shots.")
    return result


def _try_generate(prompt: str, out_path: Path, seed: int = 0) -> Path | None:
    if config.IMAGE_PROVIDER == "nvidia":
        return _try_nvidia(prompt, out_path, seed)
    return _try_pollinations(prompt, out_path, seed)


def _try_pollinations(prompt: str, out_path: Path, seed: int = 0) -> Path | None:
    """Keyless image generation via Pollinations (plain GET that returns image bytes)."""
    global _last_pollinations_call
    wait = POLLINATIONS_MIN_INTERVAL - (time.time() - _last_pollinations_call)
    if wait > 0 and _last_pollinations_call:
        time.sleep(wait)

    text = quote((prompt.strip() + STYLE_SUFFIX)[:700], safe="")
    params = f"width={GEN_WIDTH}&height={GEN_HEIGHT}&seed={seed}&model=flux&nologo=true"
    urls = [f"{base}/{text}?{params}" for base in config.POLLINATIONS_BASE_URLS]

    for url in urls:
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            _log_error(f"[image_gen] Pollinations network error: {e}")
            continue
        finally:
            _last_pollinations_call = time.time()

        if resp.ok and resp.headers.get("content-type", "").startswith("image/"):
            try:
                return _save_cover_cropped(resp.content, out_path)
            except Exception as e:  # noqa: BLE001 - corrupt image bytes
                _log_error(f"[image_gen] Could not decode Pollinations image: {e}")
        else:
            _log_error(f"[image_gen] Pollinations HTTP {resp.status_code} "
                       f"({resp.headers.get('content-type')}): {resp.text[:200]}")
    return None


def _try_nvidia(prompt: str, out_path: Path, seed: int = 0) -> Path | None:

    payload = {
        "prompt": prompt.strip() + STYLE_SUFFIX,
        "width": GEN_WIDTH,
        "height": GEN_HEIGHT,
        "seed": seed,
        "steps": 4,
    }
    if "dev" in config.NVIDIA_IMAGE_URL:
        payload.update({"mode": "base", "cfg_scale": 3.5, "steps": 30})

    headers = {
        "Authorization": f"Bearer {config.NVIDIA_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    for attempt in range(2):
        try:
            resp = requests.post(config.NVIDIA_IMAGE_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            _log_error(f"[image_gen] Network error (attempt {attempt + 1}/2): {e}")
            time.sleep(3)
            continue

        if resp.status_code == 202:
            resp = _poll_until_done(resp, headers)
            if resp is None:
                return None

        if not resp.ok:
            _log_error(f"[image_gen] HTTP {resp.status_code} from {config.NVIDIA_IMAGE_URL}: {resp.text[:300]}")
            if resp.status_code in (404, 410):  # endpoint gone, retrying will not help
                return None
            time.sleep(3)
            continue

        image_bytes = _extract_image_bytes(resp.json())
        if image_bytes is None:
            _log_error(f"[image_gen] Could not find an image in the response: {resp.text[:300]}")
            return None

        return _save_cover_cropped(image_bytes, out_path)

    return None


def _poll_until_done(resp, headers, max_wait: int = 120):
    """Some NVIDIA-hosted endpoints answer 202 and expect the client to poll for the result."""
    req_id = resp.headers.get("NVCF-REQID")
    if not req_id:
        _log_error("[image_gen] Got 202 but no NVCF-REQID header to poll with.")
        return None
    status_url = f"https://api.nvcf.nvidia.com/v2/nvcf/pexec/status/{req_id}"
    waited = 0
    while waited < max_wait:
        time.sleep(3)
        waited += 3
        try:
            poll = requests.get(status_url, headers=headers, timeout=30)
        except requests.exceptions.RequestException as e:
            _log_error(f"[image_gen] Poll error: {e}")
            continue
        if poll.status_code != 202:
            return poll
    _log_error(f"[image_gen] Gave up polling after {max_wait}s.")
    return None


def _extract_image_bytes(data: dict) -> bytes | None:
    """Accept the response shapes NVIDIA/OpenAI-style image endpoints are known to use."""
    b64 = None
    artifacts = data.get("artifacts")
    if artifacts:
        if artifacts[0].get("finishReason") not in (None, "SUCCESS"):
            return None  # e.g. CONTENT_FILTERED
        b64 = artifacts[0].get("base64")
    elif isinstance(data.get("image"), str):
        b64 = data["image"]
    elif data.get("data"):
        b64 = data["data"][0].get("b64_json")
    elif data.get("images"):
        first = data["images"][0]
        b64 = first if isinstance(first, str) else first.get("b64_json") or first.get("base64")

    if not b64:
        return None
    if "," in b64[:64]:  # strip a data-URI prefix if present
        b64 = b64.split(",", 1)[1]
    try:
        return base64.b64decode(b64)
    except ValueError:
        return None


def _save_cover_cropped(image_bytes: bytes, out_path: Path) -> Path:
    """Scale to fully cover 1080x1920 and center-crop, so ffmpeg gets an exact-size frame."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    scale = max(TARGET_WIDTH / img.width, TARGET_HEIGHT / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left = (img.width - TARGET_WIDTH) // 2
    top = (img.height - TARGET_HEIGHT) // 2
    img = img.crop((left, top, left + TARGET_WIDTH, top + TARGET_HEIGHT))
    img.save(out_path, quality=95)
    return out_path
