# SimEconomy — Technical Specification

**Version:** 1.1  
**Companion to:** `docs/PRD.md`

---

## 1. Architecture

```
Dashboard (static HTML / Next later)
        │ WebSocket + REST
Orchestrator (FastAPI)
        │
   ┌────┴────┐
   │         │
Agent     World Authority
Runtime   (ledger, markets,
(LLM +     contracts, health)
 memory)
   │         │
LLM Router  Postgres / SQLite (Phase 0: SQLite)
```

### Principles
1. **World Authority is sole mutator** of economic state.
2. Agents call **tools** with structured args; engine validates.
3. All money moves via **double-entry** transactions.
4. Simulation is **deterministic given seed** except LLM sampling (use temp=0 where possible).

---

## 2. Tick Lifecycle

```
for each tick:
  if paused: wait
  Morning:
    - process health transitions
    - deliver news / mail
    - interest accrual
  Action window:
    - schedule active agents
    - each: perceive → (optional reflect) → plan → decide → propose tools
    - World Authority executes valid proposals
  Market clearing:
    - labor matching residual
    - goods / equity order books
  Evening:
    - consumption (rule or LLM)
    - social dialogue (optional)
  EOD:
    - metrics snapshot
    - assert_ledger_balanced()
    - persist event log
```

Default: **1 tick = 1 simulated day**.

---

## 3. Data Model

### Core entities

| Entity | Key fields |
|--------|------------|
| `Agent` | id, name, role, persona_json, health, employer_id, company_id |
| `Account` | id, owner_type, owner_id, currency, balance_cents |
| `Transaction` | id, tick, debit_account, credit_account, amount_cents, memo, ref |
| `Company` | id, name, founder_id, cash_account_id, status |
| `Loan` | id, bank_id, borrower_id, principal, rate_bps, remaining, status |
| `JobPosting` | id, company_id, title, wage_cents_day, open |
| `Employment` | agent_id, company_id, wage_cents_day, active |
| `Order` | market, side, qty, price_cents, agent_id, status |
| `NewsItem` | tick, author_id, headline, body, sentiment |
| `MemoryItem` | agent_id, tick, kind, content, importance |
| `ShockEvent` | tick, type, params_json |
| `WorldState` | tick, paused, seed, policy_rate_bps |

Phase 0 uses **in-memory + SQLite** persistence. Money stored as **integer cents**.

### Invariants
- Sum of all account balances equals initial endowment total (or documented external mint only by Fed/Treasury tools).
- Every `Transaction` has matching debit/credit amounts.
- Loan disbursement creates bank asset + borrower liability + cash transfer consistently.
- Closed company cannot hire.

---

## 4. World Authority API (internal)

```python
class WorldAuthority:
    def transfer(debit, credit, amount_cents, memo, ref=None) -> Transaction
    def create_company(founder_id, name, incorporation_fee_cents) -> Company
    def apply_loan(borrower_id, bank_id, amount_cents, purpose) -> Loan | Reject
    def post_job(company_id, title, wage_cents_day) -> JobPosting
    def hire(company_id, agent_id, posting_id) -> Employment
    def run_payroll(company_id) -> list[Transaction]
    def place_order(...) -> Order
    def publish_news(author_id, headline, body, sentiment) -> NewsItem
    def set_health(agent_id, status) -> None
    def inject_shock(type, params) -> ShockEvent
    def assert_ledger_balanced() -> None
    def snapshot_metrics() -> dict
```

### Loan underwriting (Phase 0 rules)
- Borrower cash + projected income heuristic
- Max loan = min(requested, bank free reserves * cap, collateral-ish endowment rule)
- LLM may supply *narrative* recommendation; engine still decides with rules

### Sickness (Phase 0)
- Each morning: with p=`illness_rate`, healthy → sick for `sick_days` ~ Uniform(1,3)
- Sick agents skip work (no productivity, still may receive wage or not — Phase 0: unpaid sick day)
- Auto recover when sick_days remaining = 0

---

## 5. Agent Runtime

### Cognitive loop (Phase 0 simplified)
1. Build observation: cash, job, health, recent news, open postings, bank offers
2. If LLM available: call with tools schema; parse proposed actions
3. If no LLM / dry-run: **rule policy** (scripted Phase 0 demo personas)
4. Submit actions to World Authority in order
5. Append results to memory stream

### Tool schemas (Phase 0)
- `create_company(name)`
- `pay_lawyer_fee(amount_cents)` (via transfer)
- `apply_loan(amount_cents, purpose)`
- `post_job(title, wage_cents_day)`
- `apply_job(posting_id)`
- `hire(agent_id, posting_id)`
- `work()` (noop signal; engine records productivity if employed & healthy)
- `publish_article(headline, body, sentiment)`
- `consume(amount_cents)` (transfer to merchant sink)
- `noop(reason)`

### Memory
- Episodic list: `{tick, content, importance}`
- Retrieve top-k by recency × importance (no vector DB required in Phase 0)
- Reflection: every N days summarize last memories (LLM optional)

---

## 6. LLM Router

```
try providers in order:
  deepseek → kimi → minimax → openai-compatible → local
on 429/5xx/timeout: next
all fail: RulePolicy (no crash)
```

Env vars:
- `DEEPSEEK_API_KEY`, `KIMI_API_KEY` / `MOONSHOT_API_KEY`, `MINIMAX_API_KEY`
- `LOCAL_LLM_BASE_URL`, `LOCAL_LLM_MODEL`
- `SIMECONOMY_LLM_MODE=auto|cloud|local|off`

---

## 7. HTTP API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | liveness |
| GET | `/state` | tick, paused, metrics, agents summary |
| GET | `/agents` | list agents |
| GET | `/agents/{id}` | detail + memory tail |
| GET | `/accounts` | balances |
| GET | `/events` | recent events |
| GET | `/news` | news feed |
| POST | `/pause` | pause |
| POST | `/resume` | resume |
| POST | `/step` | body: `{n?: int}` |
| POST | `/shock` | body: `{type, params}` |
| POST | `/reset` | reseeds world |
| WS | `/ws` | live events |

---

## 8. Frontend (Phase 0)

Single-page dashboard served by FastAPI static files:
- Day / paused indicator
- Macro cards (cash aggregate, loans outstanding, unemployed, sick)
- Agent table with balances & roles
- Event log
- News list
- Buttons: Pause, Resume, Step 1, Step 7, Reset
- Shock form: rate_hike, illness_wave

---

## 9. Config

`config/baseline_csus.yaml` — seed, rates, endowments, illness_rate, agent definitions.

---

## 10. Testing

- `test_ledger_invariants.py` — random transfers preserve sum; reject overdraft if policy set
- `test_loan_flow.py` — apply → disburse → balances
- `test_hire_payroll.py` — hire → tick payroll
- `test_sickness.py` — sick agent skips productivity
- `test_api.py` — step / pause endpoints

CI: `pytest -q`

---

## 11. Repo layout

```
simeconomy/
  README.md
  docs/PRD.md
  docs/SPECS.md
  pyproject.toml / requirements.txt
  config/baseline_csus.yaml
  backend/
    app/main.py          # FastAPI
    engine/              # World Authority, ledger, markets
    agents/              # runtime, policies, memory
    llm/                 # router
    institutions/        # bank, fed helpers
  frontend/              # dashboard static
  scripts/seed_and_run.py
  tests/
  docker-compose.yml
```

---

## 12. Phase 0 Acceptance Checklist

1. Accounts + endowments seed correctly  
2. Founder creates company + pays lawyer  
3. Loan approve/disburse double-entry  
4. Job post → hire → wage on work days  
5. Journalist publishes; others can see news  
6. Sickness blocks work  
7. `assert_ledger_balanced()` every tick  
8. API control endpoints work  
9. Dashboard shows day, cash, events  
10. Tests pass without cloud API (`LLM_MODE=off`)

---

## 13. Security / research ethics

- Synthetic agents only; no real-person PII  
- Document LLM priors when publishing results  
- Experiments are exploratory, not financial advice
