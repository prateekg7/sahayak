"""Service for agricultural commodity prices, comparisons, and market trends (T12.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sahayak.modules.local_info.adapters.commodity import CommodityHttpDataSource
from sahayak.modules.local_info.domain.commodity import (
    format_comparison_spoken,
    format_price_spoken,
    format_trend_spoken,
    resolve_commodity,
    resolve_market,
)


class CommodityService:
    """Service providing agricultural mandi prices and market intelligence."""

    def __init__(self, data_source: CommodityHttpDataSource | None = None) -> None:
        self._data_source = data_source or CommodityHttpDataSource()

    def _calculate_days_old(self, arrival_date_str: str) -> int:
        """Calculate how many calendar days old the arrival date is."""
        try:
            arr_date = datetime.strptime(arrival_date_str, "%Y-%m-%d").date()
            today = datetime.now(UTC).date()
            diff = (today - arr_date).days
            return max(0, diff)
        except Exception:
            return 0

    async def get_price(
        self,
        commodity_query: str,
        market_query: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Retrieve latest mandi price for a commodity with unit normalization."""
        commodity = resolve_commodity(commodity_query)
        market, state = resolve_market(market_query)

        result = await self._data_source.get_price(commodity, market, state)
        record = result.data
        days_old = self._calculate_days_old(record.arrival_date)

        spoken = format_price_spoken(
            record,
            is_stale=result.is_stale,
            days_old=days_old,
        )

        data = {
            "commodity": record.commodity,
            "market": record.market,
            "state": record.state,
            "arrival_date": record.arrival_date,
            "prices": {
                "quintal": {
                    "min": record.min_price_quintal,
                    "max": record.max_price_quintal,
                    "modal": record.modal_price_quintal,
                    "currency": "INR",
                },
                "kg": {
                    "min": record.min_price_kg,
                    "max": record.max_price_kg,
                    "modal": record.modal_price_kg,
                    "currency": "INR",
                },
            },
            "source": {
                "source_id": result.source_id,
                "source_name": result.source_name,
                "license": result.license,
                "attribution": result.attribution,
                "as_of": result.effective_timestamp.isoformat(),
                "is_stale": result.is_stale or days_old > 1,
            },
        }

        return spoken, data

    async def compare_markets(
        self,
        commodity_query: str,
        market_queries: list[str],
    ) -> tuple[str, dict[str, Any]]:
        """Compare commodity prices across multiple mandis."""
        commodity = resolve_commodity(commodity_query)
        resolved_markets = [resolve_market(m) for m in market_queries if m.strip()]
        if not resolved_markets:
            resolved_markets = [
                resolve_market("Azadpur"),
                resolve_market("Ghazipur"),
            ]

        result = await self._data_source.get_market_comparison(commodity, resolved_markets)
        records = result.data

        spoken = format_comparison_spoken(
            commodity,
            records,
            is_stale=result.is_stale,
        )

        data = {
            "commodity": commodity,
            "markets": [
                {
                    "market": r.market,
                    "state": r.state,
                    "modal_price_quintal": r.modal_price_quintal,
                    "modal_price_kg": r.modal_price_kg,
                }
                for r in records
            ],
            "source": {
                "source_id": result.source_id,
                "source_name": result.source_name,
                "license": result.license,
                "attribution": result.attribution,
                "as_of": result.effective_timestamp.isoformat(),
                "is_stale": result.is_stale,
            },
        }

        return spoken, data

    async def get_trend(
        self,
        commodity_query: str,
        market_query: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Retrieve 7-day price movement and trend direction."""
        commodity = resolve_commodity(commodity_query)
        market, state = resolve_market(market_query)

        result = await self._data_source.get_trend(commodity, market, state)
        trend = result.data

        spoken = format_trend_spoken(trend, is_stale=result.is_stale)

        data = {
            "commodity": trend.commodity,
            "market": trend.market,
            "current_modal_kg": trend.current_modal_kg,
            "previous_modal_kg": trend.previous_modal_kg,
            "change_pct": trend.change_pct,
            "direction": trend.direction,
            "source": {
                "source_id": result.source_id,
                "source_name": result.source_name,
                "license": result.license,
                "attribution": result.attribution,
                "as_of": result.effective_timestamp.isoformat(),
                "is_stale": result.is_stale,
            },
        }

        return spoken, data
