# SimEconomy

**Multi-agent LLM economic simulator** — custom core.

AI agents with personas, memory, health, and goals interact through banks, companies, labor markets, media, and (later) markets and government. All money and legal state is owned by a deterministic **World Authority**; LLMs only propose actions.

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

# Seed + simulate 14 days headless
python scripts/seed_and_run.py --days 14

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

## Phase 0 scope

- Double-entry ledger (cents)
- Commercial bank loans
- Company formation + lawyer fee
- Labor: post job / hire / payroll
- Journalist + news feed
- Sickness / absenteeism
- Pause / resume / step / shock API
- Minimal web dashboard

## Architecture (one line)

`Agent Runtime (LLM|rules) → propose tools → World Authority → ledger/markets → metrics + dashboard`

## License

MIT
