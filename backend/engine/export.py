"""Research export utilities — CSV / JSON metric series."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .world import World


def export_metrics_csv(world: "World", path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = world.metrics_history
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    # union of keys
    keys: list[str] = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def export_run_json(world: "World", path: str | Path, include_agents: bool = False) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "seed": world.seed,
        "tick": world.tick,
        "config_name": world.config.get("name"),
        "phase": world.config.get("phase"),
        "metrics_history": world.metrics_history,
        "final_metrics": world.metrics,
        "companies": [c.to_dict() for c in world.companies.values()],
        "vc_deals": [d.to_dict() for d in world.vc_deals.values()],
        "market": world.market.book_snapshot(),
        "politics": world.config.get("politics", {}),
        "news_count": len(world.news),
        "events_tail": [e.to_dict() for e in world.events[-200:]],
    }
    if include_agents:
        payload["agents"] = [
            a.to_public_dict()
            | {"cash_cents": world.ledger.get(a.cash_account_id).balance_cents}
            for a in world.agents.values()
        ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def export_events_csv(world: "World", path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["tick", "kind", "message"])
        w.writeheader()
        for e in world.events:
            w.writerow({"tick": e.tick, "kind": e.kind, "message": e.message})
    return path
