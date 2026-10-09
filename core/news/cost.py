"""Cost math for news enrichment (NEWS-07). Every price is read from core/config.py's
Settings (D-01, verified against platform.claude.com on news_pricing_verified_on) --
never a literal in this module.
"""
from __future__ import annotations

from core.news.schema import Usage


def price_for(model: str, settings) -> tuple[float, float]:
    """(input $/MTok, output $/MTok) for `model`, from
    settings.news_model_prices_usd_per_mtok. Raises ValueError for any model not in that
    verified table -- there is no "default" price to fall back to."""
    for name, in_price, out_price in settings.news_model_prices_usd_per_mtok:
        if name == model:
            return in_price, out_price
    raise ValueError(f"no verified price for model {model!r}")


def cost_usd(usage: Usage, model: str, settings) -> float:
    """Total verified USD cost for one episode's usage, given its model."""
    in_price, out_price = price_for(model, settings)
    return (
        in_price * usage.input_tokens / 1e6
        + out_price * usage.output_tokens / 1e6
        + settings.news_web_search_usd_per_1k * usage.web_search_requests / 1000
    )


def ledger_total_usd(entries: list[dict]) -> float:
    """Sum of every entry's "cost_usd" field. 0.0 for an empty ledger."""
    return sum(entry["cost_usd"] for entry in entries)


def estimate_backfill_usd(
    n_episodes: int,
    model: str,
    settings,
    searches_per_episode: float,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Pre-spend budget estimate for a backfill of `n_episodes`, built from the same
    per-unit prices cost_usd uses rather than a separately maintained formula."""
    in_price, out_price = price_for(model, settings)
    per_episode = (
        settings.news_web_search_usd_per_1k * searches_per_episode / 1000
        + input_tokens * in_price / 1e6
        + output_tokens * out_price / 1e6
    )
    return n_episodes * per_episode
