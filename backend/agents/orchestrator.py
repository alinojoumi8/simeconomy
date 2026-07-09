"""Simulation tick loop with pause/resume/step + Phase 2/3 systems."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Optional

from backend.agents.runtime import AgentRuntime
from backend.engine.export import export_events_csv, export_metrics_csv, export_run_json
from backend.engine.lifecycle import process_lifecycle
from backend.engine.policy import (
    apply_fed_taylor_step,
    collect_simple_tax,
    pay_unemployment_benefits,
    run_election_if_due,
)
from backend.engine.world import World
from backend.llm.router import LLMRouter


class SimulationOrchestrator:
    def __init__(
        self,
        config_path: str | Path,
        seed: Optional[int] = None,
        use_llm: bool = False,
    ) -> None:
        self.config_path = Path(config_path)
        self.seed = seed
        self.use_llm = use_llm
        self.world = World.from_config_path(self.config_path, seed=seed)
        self.runtime = AgentRuntime(llm=LLMRouter(), use_llm=use_llm)
        self._lock = threading.RLock()
        self._auto_thread: Optional[threading.Thread] = None
        self._auto_stop = threading.Event()
        self._auto_interval_sec = 1.0

    def reset(self, seed: Optional[int] = None) -> dict[str, Any]:
        with self._lock:
            self.stop_auto()
            if seed is not None:
                self.seed = seed
            self.world = World.from_config_path(self.config_path, seed=self.seed)
            return self.world.public_state()

    def pause(self) -> dict[str, Any]:
        with self._lock:
            self.world.paused = True
            self.stop_auto()
            return {"paused": True, "tick": self.world.tick}

    def resume(self) -> dict[str, Any]:
        with self._lock:
            self.world.paused = False
            return {"paused": False, "tick": self.world.tick}

    def step(self, n: int = 1) -> dict[str, Any]:
        with self._lock:
            for _ in range(max(1, n)):
                self._run_one_tick()
            return self.world.public_state()

    def inject_shock(self, shock_type: str, params: Optional[dict] = None) -> dict[str, Any]:
        with self._lock:
            result = self.world.authority.inject_shock(shock_type, params or {})
            if hasattr(result, "to_dict"):
                return result.to_dict()
            return result

    def export_research(self, out_dir: str | Path) -> dict[str, str]:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths = {
            "metrics_csv": str(export_metrics_csv(self.world, out / "metrics.csv")),
            "events_csv": str(export_events_csv(self.world, out / "events.csv")),
            "run_json": str(export_run_json(self.world, out / "run_summary.json", include_agents=False)),
        }
        return paths

    def _active_agents_today(self) -> list[str]:
        """Scale-aware scheduling: always run key roles; sample workers."""
        w = self.world
        pop = w.config.get("population") or {}
        worker_sample = float(pop.get("worker_daily_sample", 1.0))
        key_roles = {
            "entrepreneur",
            "vc",
            "trader",
            "journalist",
            "banker",
            "lawyer",
            "economist",
            "politician",
        }
        ids: list[str] = []
        workers: list[str] = []
        for aid, a in w.agents.items():
            if not getattr(a, "alive", True):
                continue
            if a.role in key_roles:
                ids.append(aid)
            elif a.role == "worker":
                workers.append(aid)
            else:
                ids.append(aid)
        if worker_sample >= 0.999:
            ids.extend(workers)
        else:
            # deterministic sample by tick
            k = max(1, int(len(workers) * worker_sample))
            # rotate window
            if workers:
                start = (w.tick * 7) % len(workers)
                ordered = workers[start:] + workers[:start]
                ids.extend(ordered[:k])
                # always include unemployed so they can apply
                for wid in workers:
                    if not w.agents[wid].employer_company_id and wid not in ids:
                        ids.append(wid)
        return sorted(set(ids))

    def _run_one_tick(self) -> None:
        w = self.world
        w.metrics["production_units_today"] = 0
        w.metrics["sales_today"] = 0
        w.metrics["sales_cents_today"] = 0
        w.metrics["trades_today"] = 0
        w.metrics["trade_notional_cents_today"] = 0

        # Morning
        w.process_health()
        process_lifecycle(w)

        # Action window
        for agent_id in self._active_agents_today():
            agent = w.agents[agent_id]
            if not getattr(agent, "alive", True):
                continue
            actions = self.runtime.decide(w, agent)
            self.runtime.execute(w, agent, actions)

        # Market / firm operations
        w.authority.run_payroll_and_production()
        collect_simple_tax(w)
        pay_unemployment_benefits(w)
        w.authority.sell_goods_simple()
        w.authority.clear_equity_markets()

        # Policy
        apply_fed_taylor_step(w)
        run_election_if_due(w)

        # EOD
        w.tick += 1
        w.snapshot_metrics()
        w.assert_invariants()
        w.emit("tick_complete", f"End of day {w.tick - 1} → start day {w.tick}", w.metrics)

    def start_auto(self, interval_sec: float = 1.0) -> dict[str, Any]:
        with self._lock:
            self.world.paused = False
            self._auto_interval_sec = interval_sec
            if self._auto_thread and self._auto_thread.is_alive():
                return {"auto": True, "tick": self.world.tick}
            self._auto_stop.clear()

            def loop() -> None:
                while not self._auto_stop.is_set():
                    with self._lock:
                        if not self.world.paused:
                            try:
                                self._run_one_tick()
                            except Exception as e:
                                self.world.emit("error", str(e), {})
                                self.world.paused = True
                    self._auto_stop.wait(self._auto_interval_sec)

            self._auto_thread = threading.Thread(target=loop, daemon=True)
            self._auto_thread.start()
            return {"auto": True, "tick": self.world.tick}

    def stop_auto(self) -> None:
        self._auto_stop.set()
        t = self._auto_thread
        if t and t.is_alive() and threading.current_thread() is not t:
            t.join(timeout=2.0)
        self._auto_thread = None

    def state(self) -> dict[str, Any]:
        with self._lock:
            return self.world.public_state()
