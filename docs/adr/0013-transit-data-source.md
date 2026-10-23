# 0013 — Transit Data Source & Station Resolution Architecture

Status: Accepted
Date: 2026-10-24

## Context

Phase 12 Task 2 (`transit_status` tool) provides voice access to public transit departures, schedule status, and delay alerts for urban commuters and regional travelers.

Key requirements and constraints:
1. **Terms of service & legal licensing**: Many commercial transit booking sites strictly prohibit automated scraping in their terms of use. We must only integrate with official or open-licensed APIs (e.g., Open Transit API / GTFS / Open Data Delhi under ODbL 1.0 or Government Open Data License).
2. **Spoken voice input variance**: Voice users speak station names phonetically or use colloquial abbreviations ("cp" for "Rajiv Chowk", "ndls" for "New Delhi", "airport t3" for "IGI Airport", "huda" for "Millennium City Centre").
3. **Graceful degradation**: During upstream provider downtime or network glitches, the system must never leave the user hanging. It must provide standard schedule headway guidance when live tracking is unavailable.
4. **Access policy**: As public, non-sensitive civic information, transit queries permit anonymous execution (`@allow_anonymous`) per ADR 0009.

## Options Considered

1. **Third-party screen scraping of consumer booking portals**:
   - *Pros*: Covers multiple private bus lines.
   - *Cons*: Violates terms of service, fragile to HTML changes, and risks legal notices or certification failure.
2. **Open GTFS-RT / Open Transit Data Source with Fuzzy Station Resolver**:
   - *Pros*: Fully compliant with open data licenses (ODbL / Government Open Data), stable JSON payloads, fast response times compatible with Alexa+ latency budgets, and robust fuzzy station matching.
   - *Cons*: Live real-time GPS tracking is limited to supported transit networks (metro/rail/bus networks with open feeds).

## Decision

We adopt Option 2:
- **Data Source**: Open Transit API feed conforming to `BaseHttpDataSource` (ODbL 1.0 license, explicit attribution to Open Transit & Urban Transport authorities).
- **Domain Station Resolver**: A fuzzy name resolution engine mapping spoken aliases, station codes, and partial match tokens to canonical stations and operational lines (e.g., Delhi Metro Yellow, Blue, Violet, Magenta, and Airport Express lines).
- **Fallback**: Stale-while-error returns recent cached departures during transient outages; if no live feed exists, returns standard line frequency information.
- **Access Control**: Public non-persistent tool annotated with `@allow_anonymous`.

## Consequences

- Commuters get accurate, speech-friendly departure schedules under 300 characters.
- Upstream outages do not throw unhandled errors to voice users.
- Station resolution tolerates phonetic mispronunciations and colloquial nicknames.
