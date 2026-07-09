#!/usr/bin/env python3
"""Headless Phase 1 demo: seed world and run N simulated days."""

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
    parser.add_argument("--days", type=int, default=30)
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
    print(f"Companies: {m['companies']}  VC funded: {m.get('vc_funded', 0)}  Listings: {m.get('listings', 0)}")
    print(f"Loans outstanding: ${m['loans_outstanding_cents']/100:,.2f}")
    print(f"Employed workers: {m['employed_workers']}  Unemployed: {m['unemployed_workers']}")
    print(f"Sick: {m['sick_agents']}  Inventory: {m['inventory_units']}")
    print(f"Equity index: ${m.get('equity_index_cents', 0)/100:,.2f}  Trades today: {m.get('trades_today', 0)}")
    print(f"Avg opinion: {m.get('avg_opinion_economy')}  News: {m['news_count']}")
    print(f"Total money (invariant): ${m['total_money_cents']/100:,.2f}")
    print("Companies:")
    for c in state.get("companies", []):
        print(
            f"  - {c['name']} stage={c.get('stage')} symbol={c.get('listed_symbol')} "
            f"cash=${c['cash_cents']/100:,.2f} vc=${(c.get('vc_raised_cents') or 0)/100:,.2f} inv={c['inventory_units']}"
        )
    if state.get("vc_deals"):
        print("VC deals:")
        for d in state["vc_deals"]:
            print(f"  - {d['status']} ${d['amount_cents']/100:,.0f} co={d['company_id']}")
    if state.get("market", {}).get("listings"):
        print("Listings:")
        for L in state["market"]["listings"]:
            print(f"  - {L['symbol']} last=${L['last_price_cents']/100:.2f} mcap=${L['market_cap_cents']/100:,.0f}")
    if state.get("news"):
        print("Latest news:", state["news"][-1]["headline"])
    reflected = sum(1 for a in state["agents"] if a.get("reflection_count", 0) > 0)
    print(f"Agents with reflections: {reflected}/{len(state['agents'])}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(state, indent=2), encoding="utf-8")
        print("Wrote", args.json_out)


if __name__ == "__main__":
    main()
