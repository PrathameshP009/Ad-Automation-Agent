"""Apify wrapper: pulls winning Meta (Facebook/Instagram) ads for a niche via the
Meta Ad Library, using a free-tier Apify actor.

Actor choice: the Ad Library itself is public/open (no login needed to browse), and
several free Apify actors wrap it (e.g. `curious_coder/facebook-ads-library-scraper`,
`jupri/facebook-ads-scraper`). Swap APIFY_META_ADS_ACTOR_ID in .env if your account
has access to a different one — actor availability on the Store changes over time.
"""
from urllib.parse import urlencode
from apify_client import ApifyClient
import config


def build_ad_library_search_url(search_terms: str, country: str = "ALL", ad_type: str = "all",
                                    media_type: str = "all") -> str:
    """Build a Meta Ad Library search URL — this actor's `startUrls` field takes real
    Ad Library URLs (or Facebook page URLs), not raw keywords. Matches the query-param
    shape confirmed from the actor's own Input tab.
    """
    params = {
        "active_status": "active",
        "ad_type": ad_type,
        "country": country,
        "is_targeted_country": "false",
        "media_type": media_type,
        "q": search_terms,
        "search_type": "keyword_unordered",
    }
    # content_languages[0]=en needs manual encoding since urlencode mangles the brackets
    query = urlencode(params) + "&content_languages[0]=en"
    return f"https://www.facebook.com/ads/library/?{query}"


def run_meta_ads_search(search_terms: str, country: str = "ALL", ad_type: str = "all",
                          max_items: int = 60) -> list[dict]:
    """Search the Meta Ad Library for ads matching `search_terms` via a real Ad Library URL.

    Returns raw actor output items. Confirmed field shape from a live run of this actor:
    pageInfo.page_name, snapshot.title / snapshot.body (ad text — may be a DPA template
    placeholder like "{{product.name}}" for catalog-driven ads, so check for real text),
    isActive (bool), startDateFormatted / endDateFormatted (human strings, not ISO),
    spend, reachEstimate, publisherPlatform, snapshot.displayFormat.
    """
    config.require_keys("APIFY_API_TOKEN")
    client = ApifyClient(config.APIFY_API_TOKEN)

    search_url = build_ad_library_search_url(search_terms, country=country, ad_type=ad_type)

    run_input = {
        "startUrls": [{"url": search_url}],
        "resultsLimit": max_items,
        "isDetailsPerAd": True,   # per-creative detail instead of aggregated summaries — we want real ad text
        "activeStatus": "active",
        "onlyTotal": False,
        "includeAboutPage": False,
        "enrichWithEcommerceData": False,
        "sorting": "",
    }

    run = client.actor(config.APIFY_META_ADS_ACTOR_ID).call(run_input=run_input)
    dataset_id = _get_field(run, "defaultDatasetId", "default_dataset_id")
    items = list(client.dataset(dataset_id).iterate_items())
    return items


def _get_field(obj, dict_key: str, attr_name: str):
    """Newer apify-client versions return a typed Run object instead of a plain dict,
    so support both dict-style (older client) and attribute-style (newer client) access."""
    if isinstance(obj, dict):
        return obj[dict_key]
    return getattr(obj, attr_name)


def _parse_actor_date(raw: str):
    """Parse this actor's real date format, e.g. '2026-03-13 07:00:00 UTC'."""
    from datetime import datetime

    if not raw:
        return None
    cleaned = str(raw).replace(" UTC", "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=__import__("datetime").timezone.utc)
        except ValueError:
            continue
    return None


def filter_last_30_days(ads: list[dict]) -> list[dict]:
    """Keep only ads first seen running in roughly the last 30 days (still-fresh creatives,
    which per the brief is the 'what's working now' window)."""
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    kept = []
    for ad in ads:
        start = _parse_actor_date(ad.get("startDateFormatted"))
        if start is None:
            kept.append(ad)  # keep if undated rather than silently drop
            continue
        if start >= cutoff:
            kept.append(ad)
    return kept


def score_ad_strength(ad: dict) -> float:
    """Heuristic 'is this ad actually working' score from this actor's real fields:
      - isActive=True -> strong positive (still running now)
      - longer days-running (startDateFormatted -> now) -> positive (losers get killed fast)
      - reachEstimate / spend present and > 0, where Meta discloses it -> direct positive signal
      - video/display format -> required by the brief anyway
    """
    from datetime import datetime, timezone

    score = 0.0
    if ad.get("isActive"):
        score += 3.0

    start = _parse_actor_date(ad.get("startDateFormatted"))
    if start:
        days_running = (datetime.now(timezone.utc) - start).days
        score += min(days_running / 10.0, 3.0)

    reach = ad.get("reachEstimate")
    if isinstance(reach, (int, float)) and reach > 0:
        score += 2.0
    spend = ad.get("spend")
    if isinstance(spend, (int, float)) and spend > 0:
        score += 2.0

    display_format = str((ad.get("snapshot") or {}).get("displayFormat", "")).lower()
    if "video" in display_format:
        score += 2.0

    return score


def top_ads(search_terms: str, top_n: int = 10, country: str = "ALL", **kwargs) -> list[dict]:
    kwargs.setdefault("country", country)
    ads = run_meta_ads_search(search_terms, **kwargs)
    ads = filter_last_30_days(ads)
    ads.sort(key=score_ad_strength, reverse=True)
    return ads[:top_n]
