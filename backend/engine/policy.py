"""Fed / fiscal policy engine (hybrid rules + optional LLM narrative hooks)."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .world import World

from .ledger import LedgerError


def apply_fed_taylor_step(world: "World") -> dict[str, Any]:
    """
    Simple Taylor-like rule on daily data annualized loosely:
    rate_bps += 50*(inflation_gap) + 25*(u_gap)  with clamps.
    """
    pol = world.config.setdefault("policy", {})
    if not pol.get("fed_auto_adjust", True):
        return {"skipped": True}

    m = world.metrics
    inflation = float(m.get("inflation_daily", 0.0)) * 365  # crude annualization
    u = float(m.get("unemployment_rate", 0.05))
    target_i = float(pol.get("inflation_target_annual", 0.02))
    target_u = float(pol.get("natural_unemployment", 0.05))

    gap_i = inflation - target_i
    gap_u = u - target_u
    delta = int(50 * gap_i * 100 + 25 * gap_u * 100)  # coarse
    # dampen daily: only apply 1/20th
    delta = int(delta / 20)
    delta = max(-15, min(15, delta))
    old = int(pol.get("policy_rate_bps", 450))
    new = max(0, min(1200, old + delta))
    pol["policy_rate_bps"] = new
    if delta != 0:
        world.emit(
            "fed_policy",
            f"Fed adjusts policy rate {old}→{new} bps (Δ{delta})",
            {"old": old, "new": new, "inflation_ann": inflation, "u": u},
        )
    return {"old": old, "new": new, "delta": delta}


def collect_simple_tax(world: "World") -> dict[str, Any]:
    """Flat income-ish tax on employed workers wages today → treasury."""
    pol = world.config.get("policy", {})
    rate = float(pol.get("income_tax_rate", 0.0))
    if rate <= 0:
        return {"collected": 0}
    treasury = world.institutions.get("treasury")
    if not treasury:
        return {"collected": 0, "error": "no treasury"}

    collected = 0
    for emp in world.employments.values():
        if not emp.active:
            continue
        agent = world.agents.get(emp.agent_id)
        if not agent or not getattr(agent, "alive", True):
            continue
        if agent.health.value != "healthy":
            continue
        tax = int(emp.wage_cents_day * rate)
        if tax <= 0:
            continue
        try:
            world.ledger.transfer(
                agent.cash_account_id,
                treasury["cash_account_id"],
                tax,
                world.tick,
                "Income tax",
                ref="tax",
            )
            collected += tax
        except LedgerError:
            continue
    if collected:
        world.emit("tax", f"Collected ${collected/100:.2f} income tax", {"cents": collected})
    return {"collected": collected}


def pay_unemployment_benefits(world: "World") -> dict[str, Any]:
    pol = world.config.get("policy", {})
    benefit = int(pol.get("unemployment_benefit_cents_day", 0))
    if benefit <= 0:
        return {"paid": 0}
    treasury = world.institutions.get("treasury")
    if not treasury:
        return {"paid": 0}
    paid = 0
    for a in world.agents.values():
        if a.role != "worker" or not getattr(a, "alive", True):
            continue
        if a.employer_company_id:
            continue
        try:
            world.ledger.transfer(
                treasury["cash_account_id"],
                a.cash_account_id,
                benefit,
                world.tick,
                "Unemployment benefit",
                ref="ui",
                allow_overdraft=True,
            )
            paid += benefit
        except LedgerError:
            continue
    if paid:
        # benefits with overdraft may expand money supply → re-freeze conservation baseline
        world.ledger.freeze_initial_sum()
        world.emit("benefits", f"Paid UI ${paid/100:.2f}", {"cents": paid})
    return {"paid": paid}


def run_election_if_due(world: "World") -> dict[str, Any] | None:
    """Simple election every N days based on opinion + political lean."""
    pol = world.config.get("policy", {})
    interval = int(pol.get("election_interval_days", 0))
    if interval <= 0:
        return None
    if world.tick == 0 or world.tick % interval != 0:
        return None

    votes = {"left": 0, "center": 0, "right": 0}
    for a in world.agents.values():
        if not getattr(a, "alive", True):
            continue
        lean = (a.persona.political_lean or "center").lower()
        op = a.opinion_economy
        # opinion shifts ballot slightly
        if "left" in lean:
            bucket = "left" if op > -0.5 else "center"
        elif "right" in lean:
            bucket = "right" if op < 0.5 else "center"
        else:
            bucket = "center" if abs(op) < 0.25 else ("left" if op > 0 else "right")
        votes[bucket] += 1

    winner = max(votes, key=votes.get)
    world.config.setdefault("politics", {})["ruling_bloc"] = winner
    world.config["politics"]["last_election_tick"] = world.tick
    world.config["politics"]["last_votes"] = votes

    # policy reaction
    if winner == "left":
        pol["income_tax_rate"] = min(0.25, float(pol.get("income_tax_rate", 0.05)) + 0.01)
        pol["unemployment_benefit_cents_day"] = int(pol.get("unemployment_benefit_cents_day", 0)) + 500
    elif winner == "right":
        pol["income_tax_rate"] = max(0.0, float(pol.get("income_tax_rate", 0.05)) - 0.01)
        pol["unemployment_benefit_cents_day"] = max(0, int(pol.get("unemployment_benefit_cents_day", 0)) - 500)
        # hawkish nudge
        pol["policy_rate_bps"] = min(1200, int(pol.get("policy_rate_bps", 450)) + 10)

    world.emit(
        "election",
        f"Election day: {winner} bloc wins {votes}",
        {"winner": winner, "votes": votes},
    )
    for a in world.agents.values():
        if getattr(a, "alive", True):
            a.remember(world.tick, f"Election result: {winner} wins {votes}", 0.8)
    return {"winner": winner, "votes": votes}
