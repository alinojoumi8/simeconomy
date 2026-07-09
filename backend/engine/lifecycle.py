"""Birth, death, migration for Phase 3 realism."""

from __future__ import annotations

import random
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .world import World

from .models import Agent, HealthStatus, Persona, new_id
from .population import FIRST, LAST, OCCUPATIONS, LEANS


def process_lifecycle(world: "World") -> dict[str, Any]:
    pol = world.config.get("lifecycle", {})
    if not pol.get("enabled", False):
        return {"enabled": False}

    rng = world.rng
    death_p = float(pol.get("daily_death_rate", 0.0002))
    birth_p = float(pol.get("daily_birth_rate", 0.0003))
    migrate_p = float(pol.get("daily_migration_rate", 0.001))
    max_pop = int(pol.get("max_population", 2000))
    min_pop = int(pol.get("min_population", 10))

    deaths = 0
    births = 0
    migrations = 0

    alive_agents = [a for a in world.agents.values() if getattr(a, "alive", True)]

    # Death
    for a in list(alive_agents):
        # age effect
        age = getattr(a, "age", 40)
        p = death_p * (1.0 + max(0, age - 50) * 0.02)
        if a.health == HealthStatus.SICK:
            p *= 2.0
        if rng.random() < p and len(alive_agents) - deaths > min_pop:
            _kill(world, a)
            deaths += 1

    # Birth (new young workers)
    alive_now = sum(1 for a in world.agents.values() if getattr(a, "alive", True))
    if alive_now < max_pop and rng.random() < birth_p * max(1, alive_now / 50):
        # number of births scales lightly with population
        n_births = 1
        if alive_now > 200 and rng.random() < 0.3:
            n_births = 2
        for _ in range(n_births):
            if sum(1 for a in world.agents.values() if getattr(a, "alive", True)) >= max_pop:
                break
            _birth(world, rng)
            births += 1

    # Migration out (leave economy — cash removed via treasury absorption to keep ledger)
    for a in list(world.agents.values()):
        if not getattr(a, "alive", True) or a.role != "worker":
            continue
        if a.employer_company_id:
            continue
        if rng.random() < migrate_p and sum(1 for x in world.agents.values() if getattr(x, "alive", True)) > min_pop:
            _migrate_out(world, a)
            migrations += 1

    if deaths or births or migrations:
        world.emit(
            "lifecycle",
            f"Lifecycle: deaths={deaths} births={births} migrate_out={migrations}",
            {"deaths": deaths, "births": births, "migrations": migrations},
        )
    return {"deaths": deaths, "births": births, "migrations": migrations}


def _kill(world: "World", agent: Agent) -> None:
    agent.alive = False
    agent.health = HealthStatus.SICK
    # end employment
    emp = world.employments.get(agent.id)
    if emp:
        emp.active = False
    agent.employer_company_id = None
    # transfer residual cash to treasury or bank (estate)
    bal = world.ledger.get(agent.cash_account_id).balance_cents
    sink = world.institutions.get("treasury") or world.institutions.get("bank")
    if bal > 0 and sink:
        try:
            world.ledger.transfer(
                agent.cash_account_id,
                sink["cash_account_id"],
                bal,
                world.tick,
                f"Estate of {agent.name}",
                ref=agent.id,
            )
        except Exception:
            pass
    agent.remember(world.tick, "Deceased", 1.0)
    world.emit("death", f"{agent.name} died", {"agent_id": agent.id})


def _birth(world: "World", rng: random.Random) -> Agent:
    occ, skills = OCCUPATIONS[rng.randrange(len(OCCUPATIONS))]
    first = FIRST[rng.randrange(len(FIRST))]
    last = LAST[rng.randrange(len(LAST))]
    aid = new_id("born_")
    endow = int(world.config.get("endowments_cents", {}).get("worker", 500_000))
    # fund endowment from treasury/fed with overdraft then re-freeze
    source = world.institutions.get("treasury") or world.institutions.get("fed")
    cash = world.ledger.create_account("agent", aid, f"{first} {last} Cash", 0)
    if source and endow > 0:
        try:
            world.ledger.transfer(
                source["cash_account_id"],
                cash.id,
                endow,
                world.tick,
                "Birth endowment",
                ref=aid,
                allow_overdraft=True,
            )
            world.ledger.freeze_initial_sum()
        except Exception:
            pass
    persona = Persona(
        political_lean=LEANS[rng.randrange(len(LEANS))],
        risk_tolerance=round(rng.uniform(0.3, 0.7), 2),
        skills=dict(skills),
        occupation=occ,
    )
    agent = Agent(
        id=aid,
        name=f"{first} {last}",
        role="worker",
        persona=persona,
        cash_account_id=cash.id,
    )
    agent.alive = True
    agent.age = rng.randint(18, 25)
    agent.goals = ["find a good job", "earn wages", "stay healthy"]
    world.agents[aid] = agent
    agent.remember(world.tick, "Entered the economy (birth)", 0.9)
    world.emit("birth", f"{agent.name} entered the workforce", {"agent_id": aid})
    return agent


def _migrate_out(world: "World", agent: Agent) -> None:
    agent.alive = False
    emp = world.employments.get(agent.id)
    if emp:
        emp.active = False
    agent.employer_company_id = None
    bal = world.ledger.get(agent.cash_account_id).balance_cents
    sink = world.institutions.get("treasury") or world.institutions.get("bank")
    if bal > 0 and sink:
        try:
            world.ledger.transfer(
                agent.cash_account_id,
                sink["cash_account_id"],
                bal,
                world.tick,
                f"Migration outflow {agent.name}",
                ref=agent.id,
            )
        except Exception:
            pass
    world.emit("migration", f"{agent.name} migrated out", {"agent_id": agent.id})
