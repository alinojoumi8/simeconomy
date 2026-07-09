# SimEconomy

### Multi-agent LLM simulation of a US-like economy

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Phases 0–3](https://img.shields.io/badge/phases-0%E2%80%933%20complete-brightgreen.svg)](docs/PHASES.md)

**SimEconomy** is a research platform where autonomous AI agents — founders, workers, bankers, VCs, traders, journalists, politicians — interact through banks, companies, labor markets, venture capital, and stock markets.

All cash and contracts live in a deterministic **World Authority**. Language models only *propose* actions. Macro outcomes (employment, prices, credit, public opinion, elections) emerge from micro decisions.

> Not a market predictor. A laboratory for economic and social emergence.

---

## Why this exists

Classical agent-based models use hand-coded heuristics. Pure LLM sandboxes hallucinate money. SimEconomy combines both:

| Layer | Responsibility |
|-------|----------------|
| **Agents** (rules or LLM) | Goals, memory, negotiation, news, politics |
| **World Authority** | Ledger, loans, payroll, VC, order books, tax, lifecycle |
| **Experiments** | Seeds, shocks, CSV exports, live dashboard |

---

## Features (v1.0 — Phases 0–3)

- **Double-entry ledger** in integer cents with per-tick balance checks  
- **Company formation** → bank loan → hiring → production → sales  
- **VC fundraising** with equity issuance  
- **Equity IPO + limit order book** with cash/share settlement  
- **~100 agents default**, **500+** via scale config  
- **Memory + reflection** (Generative Agents style)  
- **Macro metrics**: GDP proxy, CPI, unemployment, Gini, energy index  
- **Fed** Taylor-like rate path + **fiscal** tax/benefits  
- **Lifecycle**: birth, death, migration  
- **Elections** that nudge policy  
- **Shocks**: rates, energy, illness, stimulus  
- **Research exports**: metrics CSV, events CSV, run JSON  
- **Live dashboard** + REST/WebSocket control  
- **Multi-provider LLM** (MiniMax / DeepSeek / Kimi / local) with offline rules  

---

## Quick start

```bash
git clone https://github.com/alinojoumi8/simeconomy.git
cd simeconomy
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash
# .venv\Scripts\activate       # PowerShell / cmd

pip install -r requirements.txt
pytest -q

# Headless 30-day experiment + export
python scripts/seed_and_run.py --days 30 --export exports/demo

# Live UI
uvicorn backend.app.main:app --reload --port 8000
```

Open **http://127.0.0.1:8000** — step days, inject shocks, inspect agents.

### Optional LLM

```bash
cp .env.example .env
# add MINIMAX_API_KEY / DEEPSEEK / KIMI …
python scripts/seed_and_run.py --days 7 --llm
```

No keys? Full economy still runs on the built-in **rule policy**.

---

## Example experiment output

Seed `42`, 20 days, 100 agents (rule mode):

- 2 companies founded and **IPO’d** (`NSTR`, `HORI`)  
- 2 VC rounds funded  
- Workers hired, news flowing, reflections for all agents  
- **Money conserved** every tick  
- Exports under `exports/` for analysis  

Scale check: `config/baseline_scale500.yaml` seeds **500 agents** and runs multi-day ticks with worker sampling.

---

## Architecture

```text
┌──────────────┐     tool proposals      ┌──────────────────┐
│ Agent Runtime│ ──────────────────────► │ World Authority  │
│ rules | LLM  │                         │ ledger · markets │
└──────────────┘                         │ VC · tax · Fed   │
                                         └────────┬─────────┘
                                                  │
                     ┌────────────────────────────┼────────────────────┐
                     ▼                            ▼                    ▼
               Metrics series              Dashboard / API        CSV · JSON export
```

Docs:

| Doc | Contents |
|-----|----------|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Install, API, shocks, exports |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Internals & tick pipeline |
| [docs/PRD.md](docs/PRD.md) | Product requirements |
| [docs/SPECS.md](docs/SPECS.md) | Technical specification |
| [docs/PHASES.md](docs/PHASES.md) | Phase 0–3 checklist |

---

## Project layout

```text
simeconomy/
├── backend/
│   ├── app/            # FastAPI
│   ├── engine/         # World Authority, ledger, markets, macro, lifecycle
│   ├── agents/         # runtime + orchestrator
│   └── llm/            # provider router
├── config/             # CS-US baselines (100 & 500)
├── frontend/           # dashboard
├── scripts/            # headless runner
├── tests/
└── docs/
```

---

## Configuration knobs

```yaml
population:
  target_agents: 100
  worker_daily_sample: 0.35

policy:
  income_tax_rate: 0.05
  unemployment_benefit_cents_day: 4000
  election_interval_days: 30
  fed_auto_adjust: true

lifecycle:
  enabled: true

markets:
  energy_price_index: 100.0
```

---

## API cheatsheet

```bash
curl -X POST localhost:8000/step -H 'Content-Type: application/json' -d '{"n":7}'
curl -X POST localhost:8000/shock -H 'Content-Type: application/json' \
  -d '{"type":"energy_spike","params":{"pct":40}}'
curl -X POST localhost:8000/export -H 'Content-Type: application/json' \
  -d '{"out_dir":"exports/api_run"}'
curl localhost:8000/metrics/history
```

---

## Development

```bash
pytest -q
python scripts/seed_and_run.py --days 14 --seed 7
```

Contributions welcome: issues and PRs on GitHub.

---

## Philosophy & limits

- **Synthetic agents only** — no real-person data.  
- **Exploratory science** — great for mechanism design, pedagogy, and stress tests; not investment advice.  
- LLM priors can bias narratives; document model + seed when publishing runs.

---

## License

MIT — see [LICENSE](LICENSE).

---

<p align="center">
  <b>Build a society. Watch an economy emerge.</b><br/>
  <sub>SimEconomy · custom core · Phases 0–3 complete</sub>
</p>
