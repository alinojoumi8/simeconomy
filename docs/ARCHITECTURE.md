# SimEconomy Architecture

## Design principles

1. **World Authority owns truth** — LLMs never write balances.
2. **Integer money (cents)** — no float cash.
3. **Double-entry ledger** — conservation checked each tick.
4. **Emergence over scripts** — macro comes from micro actions + policy rules.
5. **Scale by scheduling** — not every worker thinks every day.

## Package layout

```
backend/
  app/main.py           FastAPI + static dashboard
  engine/
    ledger.py           accounts + transfers
    models.py           Agent, Company, Loan, VCDeal, ...
    markets.py          equity order book
    world.py            World + WorldAuthority
    population.py       procedural workers
    macro.py            GDP/CPI/U/Gini
    policy.py           Fed Taylor, tax, UI benefits, elections
    lifecycle.py        birth/death/migration
    export.py           CSV/JSON research dumps
  agents/
    runtime.py          RulePolicy + LLM tools
    orchestrator.py     tick loop, scheduling, export
  llm/router.py         multi-provider + MiniMax Anthropic path
config/
  baseline_csus.yaml    default ~100 agents
  baseline_scale500.yaml
frontend/               dashboard SPA
scripts/seed_and_run.py
tests/
docs/
```

## Tick pipeline

1. Health transitions  
2. Lifecycle (optional)  
3. Scheduled agent decisions → tool proposals → Authority execution  
4. Payroll + production  
5. Tax + unemployment benefits  
6. Goods market clearing  
7. Equity matching + settlement  
8. Fed rate adjust + elections (if due)  
9. Tick++, metrics snapshot, ledger assert  

## Agent tools

`create_company`, `apply_loan`, `capitalize_company`, `post_job`, `apply_job`, `hire`, `work`,  
`pitch_vc`, `decide_vc`, `list_company`, `place_order`, `publish_article`, `noop`

## Institutions

- Commercial bank — loans  
- Fed — settlement + Taylor-style rate path  
- VC fund — equity financing  
- Treasury — tax sink / benefits / estates  
- Media — journalists  
- Companies — production, payroll, IPO  

## Phase map (implemented)

| Phase | Capability |
|-------|------------|
| 0 | Ledger, bank, company, hire, news, sickness, API |
| 1 | ~25→expandable cast, memory/reflection, VC, equities |
| 2 | ~100 agents, macro metrics, tax/UI, energy shocks, exports, Fed auto |
| 3 | Lifecycle, elections, 500+ scale config, population scheduling |

## Performance notes

- Rule mode: 100 agents × 30 days is sub-second to few seconds on a laptop.  
- 500 agents: use `worker_daily_sample` ~0.1–0.2.  
- LLM mode: only key roles use cloud models by default.
