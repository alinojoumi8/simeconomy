# SimEconomy agent notes

Custom multi-agent economic simulator. LLMs propose; World Authority mutates state.

## Commands

```bash
pytest -q
python scripts/seed_and_run.py --days 30 --export exports/run
uvicorn backend.app.main:app --reload --port 8000
```

## Invariants

- Integer **cents** only
- Double-entry via `Ledger.transfer`
- `assert_ledger_balanced()` every tick
- Equity + tax + lifecycle must preserve or re-freeze conservation intentionally

## Phases

0–3 complete (v1.0.0). Default config ~100 agents; `baseline_scale500.yaml` for 500.
