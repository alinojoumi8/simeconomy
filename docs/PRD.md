# SimEconomy — Product Requirements Document

**Version:** 1.1  
**Date:** July 2026  
**Status:** Approved  
**Use case:** Research / education — LLM multi-agent US-like economy simulation  
**Architecture:** Custom core (not Doxa / AgentSociety forks)

---

## 1. Vision

Build **SimEconomy**, a large-scale agent-based simulation of a US-like economy where autonomous LLM-powered agents with personas, memory, health, goals, and relationships interact through realistic institutions (banks, companies, stock market, government, media, courts). Macro outcomes (GDP, inflation, unemployment, markets, public opinion, politics) emerge from micro decisions—not hand-scripted top-down rules.

**Hard rule:** LLMs only *propose* actions. The **World Authority** validates and executes all state changes. No LLM writes balances, order books, or legal status directly.

---

## 2. Locked Decisions

| # | Topic | Decision |
|---|--------|----------|
| 1 | Baseline | Calibrated hybrid CS-US (late-2024/early-2025 style parameters, synthetic agents) |
| 2 | LLM budget | Multi-provider keys (DeepSeek, Kimi, MiniMax, …) + local fallback |
| 3 | Interaction | Real-time: pause / resume / step / shock injection |
| 4 | Gov / Fed | Hybrid: rule core + LLM committee flavor |
| 5 | Lifecycle | Birth, death, sickness, absenteeism, migration (phased) |
| 6 | Primary use | Research / education |
| 7 | UI | Web dashboard |
| 8 | Resilience | Mandatory local LLM fallback on API failure |
| 9 | Codebase | **Custom core only** — patterns inspired by Generative Agents / EconAgent / markets literature |

---

## 3. Goals & Non-Goals

### Goals
- Phase 0: 5–8 agents, ledger + loan + hire + news + sickness, invariants hold
- Phase 1: 20–30 agents, memory, dashboard, multi-provider router
- Phase 2: ~100 agents CS-US, full institution set, shocks, research exports
- Phase 3: 500–1000+ agents, deeper lifecycle and markets
- Full audit trail; reproducible experiments (seed + config hash)

### Non-Goals (MVP)
- Perfect prediction of the real US economy
- Multi-country trade
- Physical geography / 3D
- Live external market data feeds as ground truth
- Unlimited agent autonomy outside World Authority

---

## 4. Success Criteria

1. Money conserved; double-entry ledger always balances
2. Emergent macro dynamics without scripted outcomes
3. Every material action auditable
4. Pause / resume / shock works from API and dashboard
5. Cloud LLM failure falls back to local without crash
6. 30+ simulated days stable at Phase 1+

---

## 5. Functional Requirements (summary)

### Time & control
- Discrete ticks (default 1 day)
- Phases: Morning → Action → Market clearing → Social/evening → EOD
- `pause`, `resume`, `step(n)`, `inject_shock`, snapshot/restore

### Agents
- Persona, skills, personality, politics, occupation
- Health (sickness → miss work)
- Finance (engine-owned accounts)
- Social graph
- Memory stream + reflection + planning (Generative Agents style)
- Structured tool calls only for state mutation

### Institutions
Commercial banks, Fed (hybrid), companies, VC, stock exchange, government, courts, media, labor market

### Markets
Labor, goods, equities, debt, commodities — deterministic clearing

### Company path
Found → lawyer → bank loan → hire → produce/sell → optional VC/list

### Politics / opinion
News + experience → beliefs; polls; policy shocks

### Dashboard
Macro strip, agent inspector, news, shock console, event log, export

---

## 6. Non-Functional Requirements

| Area | Requirement |
|------|-------------|
| Correctness | Fail-closed on invariant break |
| Cost | Tiered models; not all agents think every tick |
| Resilience | Multi-key rotation → local endpoint |
| Observability | Action log, token usage, rejections |
| Repro | Seeded RNG, versioned configs |
| Security | No real PII; secrets in env only |

---

## 7. Phased Roadmap

### Phase 0 — Money is real (current)
5–8 agents; bank; company; labor + simple goods; ledger; loan; hire; journalist; sickness; CLI + minimal web; 14-day demo.

### Phase 1 — Society skeleton
20–30 agents; full memory; VC pitch; stock book; multi-provider + local; richer dashboard; 30-day runs.

### Phase 2 — 100 agents CS-US
Calibrated baseline; multi-sector; shocks; research exports; 90-day runs.

### Phase 3 — Scale & depth
500–1000+; birth/death; housing; elections; calibration studies.

---

## 8. Metrics

GDP proxy, CPI, unemployment, policy rate, credit growth, bankruptcy rate, Gini; firm entry/exit; loan defaults; sick days; news sentiment; tokens/tick; invariant failures (must be 0).

---

## 9. Experiment Framework

YAML-defined runs with seed, baseline, agent count, shocks, model tiers. Compare control vs treatment on metric series.

---

## 10. Risks

| Risk | Mitigation |
|------|------------|
| LLM invents money | Engine owns all numbers |
| Cost explosion | Scheduling + tiers + local |
| Incoherence | Memory + reflection |
| Non-repro science | Seeds + prompt hashes |
| No emergence | Diverse personas + shocks |

---

## 11. Approval

Approved for implementation as custom core. Phase 0 is the first shippable vertical slice.
