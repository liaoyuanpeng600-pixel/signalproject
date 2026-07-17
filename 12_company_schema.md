# 12 · Company Schema

> **Document role:** Canonical schema for the `Company` entity. Defines identity, identifiers, classification, financials snapshot, governance, and provenance. Authoritative for the entity referenced by every Signal.
>
> Requires: `00_project_context.md ≥ 0.2`, `04_data_schema.md ≥ 1.0`, `11_industry_mapping.md ≥ 0.1`.

---

## 1. Why a Company Master Exists

A Signal's `entity_ref` MUST resolve to a real Company. Without a master:
- The verifier cannot check entity validity ([02 §A3](02_agent_constitution.md))
- Aliases cannot be normalized (e.g., "Apple", "AAPL", "Apple Inc.")
- Watchlist membership is ad hoc
- Cross-Signal analytics on the same entity break

The Company master is **ground truth for what counts as a tracked entity**.

---

## 2. Identity Model

A Company has:

1. A **stable internal ID** (SIGNAL-assigned)
2. One or more **external IDs** (ticker, ISIN, CIK, etc.)
3. A **canonical name**
4. **Aliases** for entity resolution

```
Company := {
  id                : string,            // <TICKER>.<EXCHANGE> (see §3)
  ticker            : string,            // e.g., "ACME"
  exchange          : string,            // e.g., "US", "HK", "JPX"
  name              : string,            // e.g., "ACME Corporation"
  short_name?       : string,            // e.g., "ACME"
  aliases           : [string],          // alt names, prior names, common misspellings
  external_ids      : ExternalIds,
  status            : enum[active, delisted, acquired, renamed, inactive],
  classification    : Classification,
  financials        : FinancialsSnapshot?,
  governance        : Governance?,
  industry_positions: [IndustryPosition],   // see 11_industry_mapping.md §7
  watchlist         : WatchlistRef?,     // see 14_watchlist.md
  metadata          : Metadata,
  provenance        : Provenance
}
```

---

## 3. Internal ID Convention

SIGNAL assigns `<TICKER>.<EXCHANGE>` as the canonical ID:

| Exchange | Suffix | Example |
|---|---|---|
| US (NYSE, NASDAQ) | `.US` | `AAPL.US` |
| Hong Kong | `.HK` | `0700.HK` |
| Tokyo | `.JPX` | `7203.JPX` |
| Shanghai | `.SH` | `600519.SH` |
| Shenzhen | `.SZ` | `000858.SZ` |
| London | `.LON` | `HSBA.LON` |
| Frankfurt | `.FRA` | `SAP.FRA` |
| Toronto | `.TSX` | `SHOP.TSX` |

For companies listed on multiple exchanges, the **primary listing** is the canonical ID. ADRs get a separate ID with `.ADR` suffix.

When a Company delists and relists (e.g., via SPAC merger), the ID does **not** change — `status` is updated to reflect.

---

## 4. Aliases and Entity Resolution

```
aliases := [
  "Apple Inc.",
  "Apple Computer Inc",     // prior name
  "AAPL",
  "Cupertino",             // informal
]
```

The detector prompt extracts candidate entity strings; the resolver normalizes to internal ID:

```
resolver(candidate_string) -> {
  match_type: enum[exact, fuzzy, ticker, alias, none],
  company_id: string?,
  confidence: float[0,1]
}
```

| Match type | Confidence | Action |
|---|---|---|
| `exact` (canonical name) | 1.0 | Use ID directly |
| `ticker` | 0.95 | Use ID; verify exchange |
| `alias` | 0.90 | Use ID; record match |
| `fuzzy` | 0.85 × similarity | Use ID; flag in metadata |
| `none` | 0.0 | Resolution failure; Signal rejected |

A `fuzzy` match requires `confidence ≥ 0.85` to resolve; otherwise reject.

---

## 5. External Identifiers

```
ExternalIds := {
  isin?      : string,        // 12-char International Securities ID
  cusip?     : string,        // 9-char US-only
  sedol?     : string,        // 7-char UK/Ireland
  cik?       : string,        // SEC Central Index Key
  lei?       : string,        // 20-char Legal Entity Identifier
  permid?    : string,        // Refinitiv PermID
  figi?      : string         // Bloomberg FIGI
}
```

Not all fields apply to all entities. At minimum, `ticker` + `exchange` are required.

External IDs enable **deterministic** joining with external data sources (e.g., SEC EDGAR by CIK, Bloomberg by FIGI).

---

## 6. Classification

```
Classification := {
  gics_sector?     : string,        // e.g., "Information Technology"
  gics_industry?   : string,        // e.g., "Semiconductors"
  gics_subindustry?: string,        // e.g., "Semiconductors"
  sic_code?        : string,        // US SEC Standard Industrial Classification
  country_iso      : string,        // e.g., "US", "CN"
  region           : enum[americas, emea, apac, other],
  size_bucket      : enum[mega, large, mid, small, micro],   // market-cap buckets
  style            : enum[value, growth, blend, cyclical, defensive, other]
}
```

`size_bucket` thresholds (USD market cap):

| Bucket | Range |
|---|---|
| `mega` | ≥ $200B |
| `large` | $10B – $200B |
| `mid` | $2B – $10B |
| `small` | $300M – $2B |
| `micro` | < $300M |

These are recomputed quarterly from price × shares outstanding.

---

## 7. Financials Snapshot

```
FinancialsSnapshot := {
  as_of            : ISO8601,         // last update
  fiscal_year_end  : string,          // "MM-DD"
  reporting_currency : string,        // ISO 4217
  market_cap       : dollars?,
  enterprise_value?: dollars?,
  revenue_ttm?     : dollars?,         // trailing twelve months
  ebitda_ttm?      : dollars?,
  net_income_ttm?  : dollars?,
  eps_ttm?         : float?,
  pe_ttm?          : float?,
  pb?              : float?,
  ev_to_ebitda?    : float?,
  dividend_yield?  : float?,
  short_interest?  : float?,           // % of float
  beta?            : float?,
  metadata         : { source: enum[manual, sec_filing, vendor_data, computed], ... }
}
```

The snapshot is **best-effort, last-known**, not a live feed. Live prices come from a market data service (separate from Company master).

Snapshot is updated weekly. Provenance records the source.

### Why a Snapshot vs Live Data

- Live prices are continuous (not a Signal)
- The snapshot is a **reference** for the analyst to compute magnitude relative to entity size
- Stale snapshots (> 30 days) are flagged for refresh

---

## 8. Governance

```
Governance := {
  ceo?           : { name: string, since: ISO8601, source: string },
  cfo?           : { name: string, since: ISO8601, source: string },
  board_chair?   : { name: string, since: ISO8601, source: string },
  auditor?       : string,
  hq_location?   : string,
  employee_count?: int,
  founded?       : ISO8601,
  ipo_date?      : ISO8601
}
```

CEO/CFO changes are auto-detected by comparing current vs prior; a match produces a `management` Signal ([10 §3.4](10_signal_taxonomy.md)).

---

## 9. Industry Positions

See [11_industry_mapping.md §7](11_industry_mapping.md) for the binding schema. This field is **required** for any Company in the watchlist.

```
Company.industry_positions := [
  { node_id: "wafer-fab", share: 0.85, note: "Pure-play foundry" },
  { node_id: "foundry-service", share: 0.15 }
]
```

`share` sums to 1.0 ± 0.05. A Company with no positions cannot receive cross-chain reasoning.

---

## 10. Watchlist Reference

```
WatchlistRef := {
  tier           : enum[tier_1, tier_2, tier_3, tier_4],
  added_at       : ISO8601,
  added_by       : string,
  last_review_at?: ISO8601,
  notes?         : string
}
```

A Company can exist in the master without being on the watchlist (`watchlist` is null). For details on tiers and curation: [14_watchlist.md](14_watchlist.md).

---

## 11. Metadata

```
Metadata := {
  data_sources        : [string],        // e.g., ["sec_edgar", "refinitiv"]
  last_verified_at    : ISO8601,
  verification_method : enum[automated, manual, hybrid],
  known_gaps?         : [string],
  custom_tags?        : [string]
}
```

`known_gaps` flags known data limitations (e.g., "Private company, financials not disclosed").

---

## 12. Provenance

Same `Provenance` schema as Signals ([04 §6](04_data_schema.md)). For a Company, the provenance records:
- Source of name and aliases
- Source of financials snapshot
- Curator edits to any field (as `OverrideRecord[]`, see [04 §6](04_data_schema.md))

Provenance is **append-only**. Edits create new entries; the old state is preserved. Note: Curator actions on a Company use the same `OverrideRecord.action` enum as Signals, with the relevant subset (`change_tier`, `bind_industry_position`, `update_notes`, etc.). See [02 §A8](02_agent_constitution.md) for the canonical list.

---

## 13. Worked Example

```yaml
id: ACME.US
ticker: ACME
exchange: US
name: ACME Corporation
short_name: ACME
aliases:
  - "ACME Corp"
  - "Acme Co"
  - "ACME Inc"
external_ids:
  cik: "0001234567"
  isin: "US0001234567"
  cusip: "000123456"
  figi: "BBG000ABCD1"
status: active
classification:
  gics_sector: "Information Technology"
  gics_industry: "Semiconductors"
  gics_subindustry: "Semiconductors"
  sic_code: "3674"
  country_iso: "US"
  region: americas
  size_bucket: large
  style: growth
financials:
  as_of: 2026-07-15T00:00:00Z
  fiscal_year_end: "12-31"
  reporting_currency: USD
  market_cap: 15600000000
  enterprise_value: 15800000000
  revenue_ttm: 8400000000
  ebitda_ttm: 2100000000
  eps_ttm: 4.20
  pe_ttm: 18.5
  pb: 3.2
  ev_to_ebitda: 7.5
  metadata:
    source: sec_filing
governance:
  ceo: { name: "Jane Smith", since: 2022-04-01, source: "DEF 14A" }
  cfo: { name: "John Doe", since: 2023-09-15, source: "8-K" }
  auditor: "Big Four Co."
  hq_location: "San Jose, CA, USA"
  employee_count: 12500
  founded: 1998-05-12
  ipo_date: 2010-06-15
industry_positions:
  - { node_id: "wafer-fab", share: 0.85 }
  - { node_id: "foundry-service", share: 0.15 }
watchlist:
  tier: tier_1
  added_at: 2024-01-15T00:00:00Z
  added_by: curator_001
  last_review_at: 2026-07-01T00:00:00Z
  notes: "Core holding; track capacity utilization quarterly."
metadata:
  data_sources: ["sec_edgar", "refinitiv"]
  last_verified_at: 2026-07-15T00:00:00Z
  verification_method: automated
provenance:
  created_at: 2024-01-15T00:00:00Z
  created_by: curator_001
  edits:
    - at: 2026-04-02T00:00:00Z
      by: system_refresh
      field: financials
      change: "Q1 earnings update"
```

---

## 14. Adding a Company

To add a Company to the master:

1. Determine `<TICKER>.<EXCHANGE>` ID per §3
2. Populate required fields: `id`, `ticker`, `exchange`, `name`, `aliases`, `external_ids.ticker`, `classification`
3. Populate optional fields where known
4. Bind to ≥ 1 industry position if Company is in watchlist
5. Set `provenance.created_at` and `created_by`
6. Pass through entity resolver self-test: ensure all aliases resolve to this ID

Adding a Company that is **not** in the watchlist is allowed (for entity resolution enrichment).

---

## 15. Removing / Delisting

A Company is **never hard-deleted**. Instead:

| Status change | Trigger |
|---|---|
| `active → delisted` | Stock exchange delisting notice |
| `active → acquired` | M&A close confirmed |
| `active → renamed` | Official name change |
| `* → inactive` | Curator decision (e.g., too small to track) |

Status changes emit a `capital_action` Signal (if delisting/acquisition) or `management` Signal (if rename). The Company remains in the master for audit; new Signals for inactive Companies are blocked.

---

## 16. Edge Cases

| Case | Handling |
|---|---|
| Same ticker on different exchanges | Use exchange suffix to disambiguate (e.g., `SHOP.US` vs `SHOP.TSX`) |
| Company renamed | New `name`, old `name` becomes alias, ID unchanged |
| Reverse stock split | ID unchanged; tickers and aliases may be re-issued (handle in metadata) |
| Dual-class shares | Single ID; `metadata.share_classes` lists each class |
| SPAC merger | Original SPAC ID archived; new entity takes the target's effective ID with status update |
| Private company (no ticker) | ID = `PRIV.<name>`; no public-source verification possible |

---

## 17. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold |

Adding/removing required fields in §2, changes to ID convention (§3), or new identity resolution match types (§4) are MAJOR. Adding optional fields is MINOR. Wording fixes are PATCH.