"""Thin OpenAI-compatible chat client for OpenRouter or NVIDIA build.nvidia.com.

Hermes agents can plug in any provider via this callable; kept separate (instead of
relying only on Hermes' built-in provider strings) so switching OpenRouter <-> NVIDIA
build is a one-line config change, and so JSON-mode parsing is handled in one place.
"""
import json
import re
from pathlib import Path
import requests
import config

ERROR_LOG = config.ROOT / "llm_errors.log"


def _log_error(text: str) -> None:
    print(text)
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass


def chat(messages: list[dict], model: str | None = None, temperature: float = 0.7,
          max_tokens: int = 2000, json_mode: bool = False, network_retries: int = 2) -> str:
    base_url, api_key = _provider_config()
    model = model or config.LLM_MODEL_FAST

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    resp = _post_with_retry(base_url, api_key, payload, network_retries)

    if not resp.ok and json_mode:
        # Not every model/provider route supports response_format, which can surface as the
        # same "no endpoint" error as a bad model name. Retry once without it rather than
        # hard-failing — the system prompt already asks for strict JSON, so this is a
        # graceful degrade, not a silent behavior change.
        _log_error(f"[llm_client] Retrying '{model}' without response_format (got {resp.status_code}: {resp.text[:200]})")
        payload.pop("response_format", None)
        resp = _post_with_retry(base_url, api_key, payload, network_retries)

    if not resp.ok:
        _log_error(f"[llm_client] {config.LLM_PROVIDER} error {resp.status_code} for model '{model}': {resp.text[:500]}")
    resp.raise_for_status()
    message = resp.json()["choices"][0]["message"]
    content = message.get("content")
    if content is None:
        # Some free/reasoning models return content: null — e.g. when the response consists
        # only of a hidden 'reasoning' field, or the model emitted a tool_call instead of text.
        # Fall back to the reasoning field if present, else empty string so chat_json's retry
        # logic can kick in rather than crashing with an AttributeError on None.
        content = message.get("reasoning") or ""
        _log_error(f"[llm_client] Model '{model}' returned null content "
                   f"(finish_reason={resp.json()['choices'][0].get('finish_reason')}); using fallback.")
    return content


def _provider_config() -> tuple[str, str]:
    if config.LLM_PROVIDER == "nvidia":
        config.require_keys("NVIDIA_API_KEY")
        return config.NVIDIA_BASE_URL, config.NVIDIA_API_KEY
    config.require_keys("OPENROUTER_API_KEY")
    return config.OPENROUTER_BASE_URL, config.OPENROUTER_API_KEY


def _post_with_retry(base_url: str, api_key: str, payload: dict, network_retries: int):
    """Free-tier endpoints are often slower/more overloaded than paid ones, so timeouts
    happen more often — retry those specifically rather than failing the whole pipeline
    on one slow response."""
    last_exc = None
    for attempt in range(network_retries + 1):
        try:
            return _post(base_url, api_key, payload)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_exc = e
            _log_error(f"[llm_client] Network error on attempt {attempt + 1}/{network_retries + 1} "
                       f"for model '{payload.get('model')}': {e}")
    raise last_exc


def _post(base_url: str, api_key: str, payload: dict):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if config.LLM_PROVIDER == "openrouter":
        headers["HTTP-Referer"] = f"https://{config.TARGET_DOMAIN}"
        headers["X-Title"] = "CWT Video Ads Agent"

    return requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=240,  # free-tier endpoints can be noticeably slower than paid ones
    )


def chat_json(messages: list[dict], model: str | None = None, temperature: float = 0.7,
               max_tokens: int = 4000, retries: int = 2) -> dict:
    """Chat call that guarantees a parsed dict back, tolerating models that wrap JSON in prose/fences.

    Free-tier models are noticeably flakier than paid ones — some spend part of the token
    budget on hidden reasoning/safety preamble and truncate before the real answer, so this
    retries a couple of times before giving up rather than failing on the first bad output.
    """
    last_error = None
    for attempt in range(retries + 1):
        raw = chat(messages, model=model, temperature=temperature, max_tokens=max_tokens, json_mode=True)
        cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            last_error = e
            _log_error(f"[llm_client] Attempt {attempt + 1}/{retries + 1} returned non-JSON "
                  f"({len(raw)} chars): {raw[:200]!r} — retrying" if attempt < retries else "— giving up")
    raise ValueError(f"Model did not return valid JSON after {retries + 1} attempts. Last error: {last_error}")
