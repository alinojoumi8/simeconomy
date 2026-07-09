"""Procedural agent population generation for Phase 2/3 scale."""

from __future__ import annotations

import random
from typing import Any

FIRST = [
    "Alex", "Blair", "Casey", "Dana", "Eden", "Finn", "Gray", "Harper", "Indie", "Jules",
    "Kai", "Lane", "Morgan", "Noel", "Oakley", "Parker", "Quinn", "Reese", "Sage", "Taylor",
    "Uri", "Val", "Wren", "Yael", "Zion", "Avery", "Blake", "Cameron", "Drew", "Emery",
]
LAST = [
    "Nguyen", "Patel", "Garcia", "Kim", "Smith", "Johnson", "Brown", "Jones", "Miller", "Davis",
    "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White", "Harris", "Martin", "Lee",
    "Perez", "Thompson", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Hill", "Green",
]
OCCUPATIONS = [
    ("software_engineer", {"coding": 80, "product": 55}),
    ("operations", {"ops": 75, "logistics": 70}),
    ("sales", {"sales": 80, "communication": 70}),
    ("analyst", {"analysis": 78, "coding": 60}),
    ("technician", {"ops": 70, "energy": 55}),
    ("accountant", {"accounting": 85, "finance": 65}),
    ("nurse", {"healthcare": 88, "ops": 55}),
    ("teacher", {"teaching": 85, "writing": 65}),
    ("driver", {"logistics": 80, "ops": 60}),
    ("warehouse", {"ops": 72, "logistics": 75}),
    ("designer", {"design": 82, "product": 65}),
    ("customer_success", {"communication": 80, "sales": 55}),
    ("electrician", {"ops": 78, "energy": 70}),
    ("marketer", {"sales": 70, "writing": 65}),
    ("researcher", {"analysis": 80, "writing": 70}),
]
LEANS = ["left", "center-left", "center", "center-right", "right"]
SECTOR_PREF = ["tech", "energy", "retail", "healthcare", "finance", "education"]


def generate_workers(
    rng: random.Random,
    count: int,
    start_index: int = 1,
    id_prefix: str = "w",
) -> list[dict[str, Any]]:
    """Return agent config dicts compatible with baseline_csus.yaml agent entries."""
    agents: list[dict[str, Any]] = []
    for i in range(count):
        occ, skills = OCCUPATIONS[rng.randrange(len(OCCUPATIONS))]
        first = FIRST[rng.randrange(len(FIRST))]
        last = LAST[rng.randrange(len(LAST))]
        aid = f"{id_prefix}{start_index + i:04d}"
        lean = LEANS[rng.randrange(len(LEANS))]
        agents.append(
            {
                "id": aid,
                "name": f"{first} {last}",
                "role": "worker",
                "occupation": occ,
                "political_lean": lean,
                "risk_tolerance": round(rng.uniform(0.25, 0.75), 2),
                "skills": dict(skills),
                "sector_pref": SECTOR_PREF[rng.randrange(len(SECTOR_PREF))],
                "age": rng.randint(22, 64),
            }
        )
    return agents


def expand_config_agents(config: dict[str, Any], seed: int) -> dict[str, Any]:
    """
    If config.population.target_agents > len(explicit agents), append generated workers.
    Mutates a shallow copy of config.
    """
    cfg = dict(config)
    agents = list(cfg.get("agents") or [])
    pop = cfg.get("population") or {}
    target = int(pop.get("target_agents", len(agents)))
    if target <= len(agents):
        cfg["agents"] = agents
        return cfg

    rng = random.Random(seed + 991)
    need = target - len(agents)
    # avoid id collisions
    existing = {a["id"] for a in agents}
    generated = generate_workers(rng, need, start_index=1, id_prefix="w")
    # renumber if collision
    out_extra = []
    n = 1
    for g in generated:
        while g["id"] in existing:
            g["id"] = f"w{n:04d}"
            n += 1
        existing.add(g["id"])
        out_extra.append(g)
        n += 1
    cfg["agents"] = agents + out_extra
    return cfg


def generate_scale_roles(rng: random.Random, counts: dict[str, int]) -> list[dict[str, Any]]:
    """Optional extra role agents for large worlds."""
    out: list[dict[str, Any]] = []
    role_specs = {
        "journalist": ("reporter", {"writing": 85, "investigation": 70}),
        "trader": ("equity_trader", {"trading": 85, "analysis": 70}),
        "entrepreneur": ("founder", {"business": 75, "sales": 65}),
        "banker": ("loan_officer", {"finance": 80, "credit": 75}),
    }
    idx = 0
    for role, n in counts.items():
        occ, skills = role_specs.get(role, (role, {}))
        for _ in range(n):
            idx += 1
            first = FIRST[rng.randrange(len(FIRST))]
            last = LAST[rng.randrange(len(LAST))]
            out.append(
                {
                    "id": f"{role[:3]}{idx:03d}",
                    "name": f"{first} {last}",
                    "role": role,
                    "occupation": occ,
                    "political_lean": LEANS[rng.randrange(len(LEANS))],
                    "risk_tolerance": round(rng.uniform(0.3, 0.8), 2),
                    "skills": dict(skills),
                    "company_name": f"{last} { 'Labs' if role=='entrepreneur' else 'Co'}",
                }
            )
    return out
