# SimEconomy User Guide

**Version:** 1.0.0  
**Phases:** 0–3 complete

## What it is

SimEconomy is a **research multi-agent economic simulator**. LLM (or rule-based) agents act as people and institutions inside a **deterministic World Authority** that owns all money, contracts, and market state.

You can:

- Run headless experiments (seeded, reproducible structure)
- Control the sim live via REST API + web dashboard
- Inject shocks (rates, energy, illness, stimulus)
- Export metrics for analysis

## Install

```bash
git clone https://github.com/alinojoumi8/simeconomy.git
cd simeconomy
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt
```

## Quick commands

```bash
# tests
pytest -q

# 30-day headless run + research export
python scripts/seed_and_run.py --days 30 --export exports/run1

# scale config (500 agents), short run
python scripts/seed_and_run.py --config config/baseline_scale500.yaml --days 10

# dashboard
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
# open http://127.0.0.1:8000
```

## Optional LLMs

Copy keys into `.env` (gitignored). Example:

```env
SIMECONOMY_LLM_MODE=auto
MINIMAX_API_KEY=...
MINIMAX_MODEL=MiniMax-M3
MINIMAX_API_STYLE=anthropic
MINIMAX_BASE_URL=https://api.minimax.io/anthropic
```

Without keys, the **rule policy** runs the full economy offline.

Enable LLM in headless mode:

```bash
python scripts/seed_and_run.py --days 7 --llm
```

## Configs

| File | Purpose |
|------|---------|
| `config/baseline_csus.yaml` | Default full world (~100 agents, lifecycle, tax, elections) |
| `config/baseline_scale500.yaml` | Stress scale (~500 agents, lighter worker sampling) |

Key knobs:

- `population.target_agents` — expand seed cast with generated workers
- `population.worker_daily_sample` — fraction of workers who reason each day
- `policy.income_tax_rate`, `unemployment_benefit_cents_day`
- `policy.election_interval_days`
- `lifecycle.*` — birth / death / migration rates
- `markets.energy_price_index`

## API surface

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | version + phase |
| GET | `/state` | full snapshot |
| GET | `/agents`, `/agents/{id}` | inspector |
| GET | `/market`, `/vc`, `/news`, `/events` | markets & media |
| GET | `/metrics/history` | time series |
| POST | `/step` | `{ "n": 7 }` |
| POST | `/pause`, `/resume` | control |
| POST | `/shock` | `{ "type", "params" }` |
| POST | `/reset` | reseeds world |
| POST | `/auto/start`, `/auto/stop` | live ticking |
| POST | `/export` | write CSV/JSON under `out_dir` |

### Shock types

- `rate_hike` / `rate_cut` — `{ "bps": 50 }`
- `illness_wave` — `{ "rate": 0.5, "days": 3 }`
- `energy_spike` / `energy_drop` — `{ "pct": 40 }`
- `cash_grant` — `{ "amount_cents": 50000 }`

## Exports

Headless:

```bash
python scripts/seed_and_run.py --days 90 --export exports/exp_a
```

Produces:

- `metrics.csv` — daily macro series
- `events.csv` — event log
- `run_summary.json` — companies, VC, market, metrics history

## Architecture (short)

```
Agents (rules | LLM)
   │ propose tools
   ▼
World Authority
   │ validates
   ▼
Ledger · Labor · Goods · VC · Equities · Tax · Fed · Lifecycle
   │
   ▼
Metrics · Dashboard · CSV/JSON export
```

**Invariant:** money is integer cents; double-entry ledger must balance after every tick.

## Research tips

1. Fix `seed` for comparable runs.
2. Change one policy knob at a time (tax, energy, rates).
3. Export metrics and compare series offline.
4. Use rule mode for bulk experiments; LLM for narrative deep-dives on fewer agents.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| LLM not used | Set keys + `SIMECONOMY_LLM_MODE=auto`; pass `--llm` for CLI |
| Slow with 500 agents | Lower `worker_daily_sample`; keep rule mode |
| Ledger imbalance | Should never happen — run `pytest`; file an issue with seed |
| Port 8000 in use | Change port or stop old uvicorn |
