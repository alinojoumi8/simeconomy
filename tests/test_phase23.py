from pathlib import Path

from backend.agents.orchestrator import SimulationOrchestrator
from backend.engine.export import export_metrics_csv, export_run_json
from backend.engine.world import World

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "baseline_csus.yaml"
SCALE = ROOT / "config" / "baseline_scale500.yaml"


def test_population_expands_to_100():
    w = World.from_config_path(CONFIG, seed=1)
    assert len(w.agents) >= 100
    assert "treasury" in w.institutions
    w.assert_invariants()


def test_energy_shock_and_macro_fields():
    orch = SimulationOrchestrator(CONFIG, seed=3, use_llm=False)
    orch.step(3)
    r = orch.inject_shock("energy_spike", {"pct": 50})
    assert r.get("ok") is True
    orch.step(2)
    m = orch.world.metrics
    assert "gdp_proxy_cents" in m
    assert "cpi" in m
    assert "unemployment_rate" in m
    assert m["energy_price_index"] >= 140
    orch.world.assert_invariants()


def test_export_research_artifacts(tmp_path):
    orch = SimulationOrchestrator(CONFIG, seed=5, use_llm=False)
    orch.step(5)
    paths = orch.export_research(tmp_path / "out")
    assert Path(paths["metrics_csv"]).exists()
    assert Path(paths["run_json"]).exists()
    assert Path(paths["metrics_csv"]).stat().st_size > 0


def test_lifecycle_and_election_hooks():
    orch = SimulationOrchestrator(CONFIG, seed=9, use_llm=False)
    # force high lifecycle rates temporarily
    orch.world.config["lifecycle"]["daily_death_rate"] = 0.05
    orch.world.config["lifecycle"]["daily_birth_rate"] = 0.1
    orch.world.config["policy"]["election_interval_days"] = 5
    state = orch.step(10)
    assert state["tick"] == 10
    # politics should exist
    assert "ruling_bloc" in (state.get("politics") or {}) or "ruling_bloc" in state["metrics"]
    orch.world.assert_invariants()


def test_thirty_day_full_config():
    orch = SimulationOrchestrator(CONFIG, seed=42, use_llm=False)
    state = orch.step(30)
    assert state["tick"] == 30
    assert state["metrics"]["agent_count"] >= 100
    assert state["metrics"]["companies"] >= 1
    orch.world.assert_invariants()


def test_scale_config_seeds_500():
    w = World.from_config_path(SCALE, seed=2)
    assert len(w.agents) >= 500
    w.assert_invariants()
