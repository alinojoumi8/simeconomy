# Phase 1 Implementation Notes

**Status:** shipped (v0.2.0)

## Delivered

1. **~25 agents** across roles: entrepreneurs, workers, lawyers, bankers, VC, traders, journalists, economist, politician.
2. **Memory + reflection** — episodic memory stream; rule-based reflections every 5 days (LLM optional).
3. **VC path** — `pitch_vc` → `decide_vc` → fund transfer from Apex Ventures + equity shares.
4. **Equity market** — IPO via `list_company`, limit order book, cash+share settlement, money conserved.
5. **Opinion dynamics** — agents' `opinion_economy` drifts with news sentiment.
6. **Dashboard** — agent inspector, VC panel, market panel, 30-day step, macro cards for listings/VC/opinion.
7. **API** — `/market`, `/vc`, `/metrics/history` added.

## Exit criteria (met)

- 30-day rule-policy run stable
- Ledger always balanced
- ≥1 company, VC funding, listings, news, reflections across population

## Known Phase 1 limits

- Order book is single-price-time match per day (no continuous matching intra-tick beyond one clear)
- VC underwriting is simple rule-based
- No multi-asset portfolio MTM on dashboard yet
- LLM still opt-in (`--llm` / env keys)

## Next (Phase 2)

- Scale toward ~100 agents with demographic calibration
- Multi-sector production (energy shocks affecting costs)
- Richer Fed / fiscal policy agents
- Research export (CSV/Parquet of metric series)
