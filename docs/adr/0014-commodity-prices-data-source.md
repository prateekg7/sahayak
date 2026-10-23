# 0014 — Agricultural Commodity Prices Data Source & Unit Normalization

Status: Accepted
Date: 2026-10-24

## Context

Phase 12 Task 3 (`commodity_prices` tool) enables voice users (farmers, small vendors, households) to inquire about agricultural crop prices, mandi comparisons, and market trends (e.g., "What is the wheat price in Azadpur mandi?", "Compare onion prices between Azadpur and Ghazipur", "Is tomato price going up?").

Key requirements and constraints:
1. **Legal & Licensing Compliance**: Integration must use official government open data sources (Agmarknet / Open Government Data Platform India `data.gov.in`) governed by the Government Open Data License (GODL-India), strictly avoiding commercial web scraping.
2. **Unit Normalization**: Wholesale markets report prices in Rs per Quintal (100 kg). Everyday shoppers and small vendors often think in Rs per Kilogram. The tool must provide both representations clearly.
3. **Freshness & Holiday Awareness**: Mandis operate on trading days (closed on Sundays and state holidays). Prices may be 24–48 hours old on non-trading days. A freshness guard must warn the user when data is from a previous trading session.
4. **Colloquial Multilingual Aliasing**: Crop names must be recognized across common English and Hindi colloquial terms ("gehun" for wheat, "pyaz" for onion, "aloo" for potato, "tamatar" for tomato, "chana" for gram).
5. **Access Policy**: Read-only, non-sensitive public data allows anonymous access (`@allow_anonymous`) per ADR 0009.

## Options Considered

1. **Third-Party Agri-Tech Aggregator APIs**:
   - *Pros*: Pre-packaged averages.
   - *Cons*: Restrictive commercial licensing, paywalls, unpredictable rate limits, and vendor lock-in.
2. **Open Government Data (Agmarknet / data.gov.in) via `BaseHttpDataSource`**:
   - *Pros*: Official public record, royalty-free GODL-India license, direct mandi-level granularity, resilient caching (2-tier fresh + stale) with automatic circuit breaking.
   - *Cons*: Trading closures cause reporting lags on weekends, requiring explicit voice freshness indicators.

## Decision

We adopt Option 2:
- **Data Source**: Agmarknet Open Data Feed via `BaseHttpDataSource` with allow-listed domains (`api.data.gov.in`, `agmarknet.gov.in`, `api.agmarknet.in`).
- **Domain Aliasing Engine**: Bidirectional phonetic dictionary for commodities (wheat, rice, onion, potato, tomato, mustard, gram, maize) and major regional wholesale mandis (Azadpur, Ghazipur, Okhla, Narela, Khanna, Lasalgaon, Karnal).
- **Unit Normalization**: Integer arithmetic converting quintal wholesale prices to per-kilogram retail indicators.
- **Freshness Guard**: Date verification appending natural speech warnings (e.g., "Prices as of Friday; markets are closed today") when data is older than 24 hours.
- **Tool Surface**: `commodity_prices` tool supporting `get_price`, `compare_markets`, and `trend` actions, annotated with `@allow_anonymous`.

## Consequences

- Farmers and consumers receive verified wholesale prices in both quintal and kilogram units under 300 characters.
- Weekend trading closures are handled gracefully without misleading users about real-time market activity.
- Voice users can inquire using either Hindi or English commodity names.
