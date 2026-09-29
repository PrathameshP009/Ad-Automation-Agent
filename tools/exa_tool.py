"""Exa neural search wrapper — used alongside Tavily for a second, differently-biased
set of research results (Exa's neural search tends to surface more essay/analysis-style
content vs Tavily's more news-weighted results, which is useful for finding genuine ICP
pain-point language rather than just headlines)."""
import config


def search_pain_point(query: str, max_results: int = 8) -> list[dict]:
    from exa_py import Exa

    config.require_keys("EXA_API_KEY")
    exa = Exa(api_key=config.EXA_API_KEY)

    resp = exa.search_and_contents(
        query,
        num_results=max_results,
        start_published_date=_one_month_ago_iso(),
        type="neural",
        text={"max_characters": 1000},
    )
    return [
        {
            "title": r.title,
            "url": r.url,
            "content": r.text,
            "published_date": r.published_date,
        }
        for r in resp.results
    ]


def _one_month_ago_iso() -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
