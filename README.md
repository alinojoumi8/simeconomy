# SimEconomy

**Version:** 0.2.0 (Phase 1)

Multi-agent LLM economic simulator — **custom core**.

AI agents with personas, **memory/reflection**, health, and goals interact through banks, companies, **VC**, **equity markets**, labor markets, and media. All money and legal state is owned by a deterministic **World Authority**; LLMs only propose actions.

- **PRD:** [docs/PRD.md](docs/PRD.md)
- **Technical specs:** [docs/SPECS.md](docs/SPECS.md)

## Quick start

```bash
# Python 3.11+
cd simeconomy
python -m venv .venv
# Windows: .venv\Scripts\activate
# Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt

# Run tests (no API keys required)
pytest -q

# Seed + simulate 30 days headless
python scripts/seed_and_run.py --days 30

# API + dashboard
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
# open http://127.0.0.1:8000
```

### Optional LLM keys

```bash
export DEEPSEEK_API_KEY=...
export MOONSHOT_API_KEY=...   # Kimi
export MINIMAX_API_KEY=...
export SIMECONOMY_LLM_MODE=auto   # auto | cloud | local | off
export LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1
export LOCAL_LLM_MODEL=qwen2.5:7b
```

Without keys, agents use the built-in **rule policy** (fully runnable demo).

## Phase 1 scope

- ~25 agents (founders, workers, VC, traders, journalists, economist, politician, …)
- Generative-Agents-style episodic memory + periodic **reflection**
- **VC pitch / fund** with equity issuance
- **Equity order book** + IPO path + trade settlement
- Opinion drift from news
- Dashboard: agent inspector, VC deals, market panel, shocks

## Architecture (one line)

`RulePolicy | LLM → tool proposals → World Authority → ledger / VC / equities → metrics + dashboard`

## License

MIT
