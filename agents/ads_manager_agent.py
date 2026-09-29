"""Agent 1 — Ads Manager Agent.

Sources currently-winning Meta ads in the trading/fintech niche via Apify, then uses
an LLM pass to extract the marketing concept, pain point, and visual pattern from each,
so the Script Agent has real, working creative DNA to build on instead of guessing.
"""
import json
from hermes.core import Agent

import config
from tools import apify_tool, llm_client

EXTRACTION_SYSTEM_PROMPT = """You are a senior direct-response ad strategist. Given a
Meta ad's copy/transcript, extract its creative DNA in strict JSON:
{
  "pain_point": "the core fear/frustration/desire the ad exploits",
  "marketing_angle": "the specific hook/angle used (e.g. 'insider secret', 'social proof', 'fear of missing the move')",
  "cta_style": "how it asks for the click (e.g. 'urgency', 'free trial', 'curiosity gap')",
  "visual_pattern": "one of: talking_head | data_overlay | ugc_testimonial | cinematic_broll | screen_record | meme_format",
  "why_it_works": "one sentence on the psychological mechanism"
}
Return ONLY the JSON object, nothing else."""


def build_agent() -> Agent:
    return Agent(
        provider="openai",  # OpenAI-compatible; base_url points at OpenRouter, see tools/llm_client.py
        model=config.LLM_MODEL_FAST,
        name="AdsManagerAgent",
        description="Sources and analyzes currently-winning Meta ads for a given product/niche.",
        prompt=(
            "You source and analyze the best-performing running ads in a niche from the "
            "Meta Ad Library and extract what makes each one work."
        ),
    )


def _extract_ad_text(ad: dict) -> str:
    """Pull real ad copy from this actor's nested `snapshot` object, skipping DPA
    template placeholders like '{{product.name}}' which carry no real marketing language
    (those come from catalog-driven Dynamic Product Ads and won't have a fixed hook to learn from).
    """
    snapshot = ad.get("snapshot") or {}
    candidates = [
        snapshot.get("title"),
        (snapshot.get("body") or {}).get("text") if isinstance(snapshot.get("body"), dict) else snapshot.get("body"),
        snapshot.get("linkDescription"),
        snapshot.get("caption"),
    ]
    for c in candidates:
        if c and "{{" not in str(c):  # skip unresolved DPA template tokens
            return str(c)
    return ""


def extract_concept(ad: dict) -> dict:
    ad_text = _extract_ad_text(ad)
    if not ad_text:
        return {"pain_point": None, "marketing_angle": None, "cta_style": None,
                 "visual_pattern": None, "why_it_works": None, "_note": "no ad copy/transcript available"}

    page_name = (ad.get("pageInfo") or {}).get("page_name", "unknown")
    result = llm_client.chat_json(
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Ad copy:\n{ad_text}\n\nPage/advertiser: {page_name}"},
        ],
        model=config.LLM_MODEL_FAST,
        temperature=0.3,
    )
    return result


def run(product: str = None, niche: str = None, top_n: int = 10) -> list[dict]:
    """Full Agent-1 pipeline: search -> filter/score -> extract concepts -> save JSON."""
    product = product or config.TARGET_PRODUCT
    niche = niche or config.TARGET_NICHE
    search_terms = f"{product} {niche}"

    ads = apify_tool.top_ads(search_terms, top_n=top_n)

    enriched = []
    for ad in ads:
        concept = extract_concept(ad)
        snapshot = ad.get("snapshot") or {}
        enriched.append({
            "page_name": (ad.get("pageInfo") or {}).get("page_name"),
            "is_active": ad.get("isActive"),
            "start_date": ad.get("startDateFormatted"),
            "end_date": ad.get("endDateFormatted"),
            "display_format": snapshot.get("displayFormat"),
            "spend": ad.get("spend"),
            "reach_estimate": ad.get("reachEstimate"),
            "raw_copy": _extract_ad_text(ad)[:1000],
            "concept": concept,
        })

    out_path = config.OUTPUT_DIR / "ads.json"
    out_path.write_text(json.dumps({
        "product": product, "niche": niche, "search_terms": search_terms, "ads": enriched,
    }, indent=2))
    print(f"[AdsManagerAgent] Saved {len(enriched)} analyzed ads to {out_path}")
    return enriched


if __name__ == "__main__":
    run()
