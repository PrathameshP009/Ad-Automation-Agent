"""Agent 2 — Script Agent.

For each of 3 script "types" (angles derived from the top pain points Agent 1 found),
researches the pain point + ICP behavior via Tavily/Exa (last 30 days), folds in CWT's
unique data assets, and writes a cinematic 30-60s storyboard as structured JSON.
"""
import json
from pathlib import Path
from hermes.core import Agent

import config
from tools import tavily_tool, exa_tool, llm_client

STORYBOARD_SYSTEM_PROMPT = """You are an award-winning direct-response video ad director,
known for cinematic, high-retention short-form ads (think: the visual polish of a movie
trailer combined with the hook discipline of a top-performing Meta ad). You never write
"text ads" (static copy) — every output is a shot-by-shot cinematic storyboard.

Rules:
- The ad is 30-60 seconds total.
- Shot 1 (0-3s) MUST be a pattern-interrupt visual hook that stops the scroll BEFORE any
  branding or CTA appears. No logos, no "Introducing X" in shot 1.
- Use real data/proof points where given (from research + CrowdWisdomTrading's unique data).
- Write concrete camera/visual direction, not vague mood words ("cinematic slow-motion
  overhead shot of a red candlestick chart crashing through a trader's phone screen" not
  "exciting visuals").
- Output STRICT JSON matching this schema, nothing else:
{
  "title": "short ad title",
  "angle": "the pain/marketing angle this version targets",
  "target_icp": "who this is for",
  "total_duration_sec": 45,
  "shots": [
    {
      "shot_number": 1,
      "timecode": "0:00-0:03",
      "duration_sec": 3,
      "visual": "concrete camera/visual direction",
      "vo_line": "voiceover line, or empty string if none",
      "on_screen_text": "burned-in caption text, or empty string",
      "sfx_music_cue": "music/sfx direction"
    }
  ],
  "cta": {"line": "final CTA voiceover/text", "visual": "final shot direction"}
}"""


def build_agent() -> Agent:
    return Agent(
        provider="openai",
        model=config.LLM_MODEL_CREATIVE,
        name="ScriptAgent",
        description="Researches pain points/ICP and writes cinematic video ad storyboards.",
        prompt=STORYBOARD_SYSTEM_PROMPT,
    )


def research_pain_point(pain_point: str, icp: str) -> dict:
    query = f"{pain_point} {icp}"
    tavily_results, exa_results = [], []
    try:
        tavily_results = tavily_tool.search_pain_point(query)
    except Exception as e:  # noqa: BLE001
        print(f"[ScriptAgent] Tavily search failed: {e}")
    try:
        exa_results = exa_tool.search_pain_point(query)
    except Exception as e:  # noqa: BLE001
        print(f"[ScriptAgent] Exa search failed: {e}")

    combined = (tavily_results or []) + (exa_results or [])
    return {
        "query": query,
        "sources": [
            {"title": r.get("title"), "url": r.get("url"), "snippet": (r.get("content") or "")[:400]}
            for r in combined[:10]
        ],
    }


def load_unique_data() -> str:
    path = Path(__file__).parent.parent / "prompts" / "unique_data.md"
    if path.exists():
        return path.read_text()
    return "(No unique data file found — fill in prompts/unique_data.md with CWT's proprietary data assets.)"


def write_storyboard(pain_point: str, marketing_angle: str, icp: str, research: dict) -> dict:
    unique_data = load_unique_data()
    user_prompt = f"""Product: {config.TARGET_PRODUCT}
Brand: {config.TARGET_DOMAIN} (CrowdWisdomTrading)
ICP: {icp}
Pain point / angle to target: {pain_point} — marketing angle: {marketing_angle}

Recent research on this pain point (last 30 days):
{json.dumps(research['sources'], indent=2)}

CrowdWisdomTrading's unique data / differentiators to weave in as proof:
{unique_data}

Write the cinematic storyboard now, per the schema and rules in your system prompt."""

    return llm_client.chat_json(
        messages=[
            {"role": "system", "content": STORYBOARD_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        model=config.LLM_MODEL_CREATIVE,
        temperature=0.9,
        max_tokens=6000,
    )


def run(ads_json_path: str = None, num_scripts: int = 3) -> list[dict]:
    ads_json_path = ads_json_path or (config.OUTPUT_DIR / "ads.json")
    data = json.loads(Path(ads_json_path).read_text())
    ads = data.get("ads", [])
    icp = data.get("niche", config.TARGET_NICHE)

    # Take up to `num_scripts` distinct pain points from Agent 1's output
    seen_pains = []
    for ad in ads:
        pain = (ad.get("concept") or {}).get("pain_point")
        angle = (ad.get("concept") or {}).get("marketing_angle")
        if pain and pain not in [p for p, _ in seen_pains]:
            seen_pains.append((pain, angle))
        if len(seen_pains) >= num_scripts:
            break

    if not seen_pains:
        seen_pains = [
            ("Retail traders lose money because they trade on emotion, not data", "insider data edge"),
            ("Traders miss big moves because they can't watch the market all day", "automation / never miss a signal"),
            ("Most 'signal services' are black boxes with no real track record", "transparency / proof"),
        ][:num_scripts]

    storyboards = []
    for i, (pain, angle) in enumerate(seen_pains, start=1):
        research = research_pain_point(pain, icp)
        storyboard = write_storyboard(pain, angle or "unspecified", icp, research)
        storyboard["_research"] = research
        out_path = config.OUTPUT_DIR / f"script_{i}.json"
        out_path.write_text(json.dumps(storyboard, indent=2))
        print(f"[ScriptAgent] Saved storyboard {i} ({pain[:50]}...) to {out_path}")
        storyboards.append(storyboard)

    return storyboards


if __name__ == "__main__":
    run()
