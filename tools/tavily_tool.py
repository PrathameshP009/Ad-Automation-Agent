"""Tavily search wrapper, scoped to the last month per the brief.

Note: the pip package is `tavily-python` but it's imported as `tavily`.
"""
import config


def _client():
    from tavily import TavilyClient
    config.require_keys("TAVILY_API_KEY")
    return TavilyClient(api_key=config.TAVILY_API_KEY)


def search_pain_point(query: str, max_results: int = 8) -> list[dict]:
    """Search recent (last month) discussion of a trading pain point / ICP behavior.

    Returns list of {title, url, content, score, published_date}.
    """
    client = _client()
    resp = client.search(
        query=query,
        search_depth="advanced",
        topic="general",
        time_range="month",
        max_results=max_results,
        include_answer=False,
    )
    return resp.get("results", [])
