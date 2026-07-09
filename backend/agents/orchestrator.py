"""Simulation tick loop with pause/resume/step."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Optional

from backend.agents.runtime import AgentRuntime
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

    def _run_one_tick(self) -> None:
        w = self.world
        w.metrics["production_units_today"] = 0
        w.metrics["sales_today"] = 0
        w.metrics["sales_cents_today"] = 0
        w.metrics["trades_today"] = 0
        w.metrics["trade_notional_cents_today"] = 0

        # Morning
        w.process_health()

        # Action window — stable order by id
        for agent_id in sorted(w.agents.keys()):
            agent = w.agents[agent_id]
            actions = self.runtime.decide(w, agent)
            self.runtime.execute(w, agent, actions)

        # Market / firm operations
        w.authority.run_payroll_and_production()
        w.authority.sell_goods_simple()
        w.authority.clear_equity_markets()

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
