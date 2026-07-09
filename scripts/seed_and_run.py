#!/usr/bin/env python3
"""Headless Phase 0 demo: seed world and run N simulated days."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.agents.orchestrator import SimulationOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SimEconomy headless simulation")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--config", type=str, default=str(ROOT / "config" / "baseline_csus.yaml"))
    parser.add_argument("--llm", action="store_true", help="Enable LLM if keys configured")
    parser.add_argument("--json-out", type=str, default="")
    args = parser.parse_args()

    orch = SimulationOrchestrator(args.config, seed=args.seed, use_llm=args.llm)
    print(f"Seeded world seed={args.seed} agents={len(orch.world.agents)}")
    print(f"Initial total money: ${orch.world.ledger.total_money()/100:,.2f}")

    state = orch.step(args.days)
    m = state["metrics"]
    print("--- after", args.days, "days ---")
    print(f"Day: {state['tick']}")
    print(f"Companies: {m['companies']}")
    print(f"Loans outstanding: ${m['loans_outstanding_cents']/100:,.2f}")
    print(f"Employed workers: {m['employed_workers']}  Unemployed: {m['unemployed_workers']}")
    print(f"Sick: {m['sick_agents']}  Inventory: {m['inventory_units']}")
    print(f"Total money (invariant): ${m['total_money_cents']/100:,.2f}")
    print(f"News items: {m['news_count']}")
    print("Agents:")
    for a in state["agents"]:
        print(f"  - {a['name']:16} {a['role']:12} cash=${a['cash_cents']/100:>10,.2f} health={a['health']}")
    if state["companies"]:
        print("Companies:")
        for c in state["companies"]:
            print(f"  - {c['name']} cash=${c['cash_cents']/100:,.2f} inv={c['inventory_units']}")
    if state["news"]:
        print("Latest news:", state["news"][-1]["headline"])

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(state, indent=2), encoding="utf-8")
        print("Wrote", args.json_out)


if __name__ == "__main__":
    main()
