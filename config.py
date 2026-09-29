"""Central configuration, loaded from environment / .env."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
OUTPUT_DIR = ROOT / os.getenv("VIDEO_OUTPUT_DIR", "outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# --- LLM ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "nvidia")  # "nvidia" or "openrouter"

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "pollinations")  # "pollinations" (keyless) or "nvidia"
POLLINATIONS_BASE_URLS = [
    "https://image.pollinations.ai/prompt",
    "https://gen.pollinations.ai/image",
]
NVIDIA_IMAGE_URL = os.getenv(
    "NVIDIA_IMAGE_URL", "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-schnell"
)

LLM_MODEL_FAST = os.getenv("LLM_MODEL_FAST", "meta/llama-3.2-11b-vision-instruct")
LLM_MODEL_CREATIVE = os.getenv("LLM_MODEL_CREATIVE", "meta/llama-3.2-11b-vision-instruct")

# --- Data sources ---
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")
APIFY_META_ADS_ACTOR_ID = os.getenv("APIFY_META_ADS_ACTOR_ID", "curious_coder/facebook-ads-library-scraper")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
EXA_API_KEY = os.getenv("EXA_API_KEY", "")

# --- Target brand ---
TARGET_DOMAIN = os.getenv("TARGET_DOMAIN", "crowdwisdomtrading.com")
TARGET_PRODUCT = os.getenv("TARGET_PRODUCT", "algorithmic trading signals")
TARGET_NICHE = os.getenv("TARGET_NICHE", "retail day traders")

# --- Video ---
OPENMONTAGE_REPO_PATH = os.getenv("OPENMONTAGE_REPO_PATH", "../OpenMontage")
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-GuyNeural")


def require_keys(*names: str) -> None:
    """Fail loudly and early if a required key is missing, instead of failing deep in an API call."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise RuntimeError(
            f"Missing required config: {', '.join(missing)}. "
            f"Copy .env.example to .env and fill these in."
        )
