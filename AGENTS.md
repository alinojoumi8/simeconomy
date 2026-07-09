# SimEconomy agent notes

Custom multi-agent economic simulator. LLMs propose; World Authority mutates state.

## Commands

```bash
# from repo root, venv active
pytest -q
python scripts/seed_and_run.py --days 14
uvicorn backend.app.main:app --reload --port 8000
```

## Invariants

- All money is integer **cents**
- Double-entry only via `Ledger.transfer`
- `assert_ledger_balanced()` after every tick
- Never let LLM write balances directly

## Phase map

- Phase 0 (done): ledger, bank loan, company, hire, news, sickness, API, dashboard
- Phase 1: richer memory/reflection, VC, stock book, multi-provider live agents
- Phase 2: ~100 agents CS-US baseline
