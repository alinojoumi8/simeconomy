from pathlib import Path

from backend.agents.orchestrator import SimulationOrchestrator
from backend.engine.world import World

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "baseline_csus.yaml"


def test_seed_has_phase1_agents_and_vc_fund():
    w = World.from_config_path(CONFIG, seed=1)
    assert len(w.agents) >= 20
    assert "vc" in w.institutions
    assert any(a.role == "vc" for a in w.agents.values())
    assert any(a.role == "trader" for a in w.agents.values())
    w.assert_invariants()


def test_vc_pitch_and_fund_conserves_money():
    w = World.from_config_path(CONFIG, seed=2)
    before = w.ledger.total_money()
    r = w.authority.create_company("alice", "Northstar Labs")
    assert r["ok"]
    co_id = w.agents["alice"].founded_company_id
    pitch = w.authority.pitch_to_vc("alice", co_id, 5_000_000, "scale product")
    assert pitch["ok"]
    deal_id = pitch["deal"]["id"]
    vc_id = pitch["deal"]["vc_agent_id"]
    fund = w.authority.decide_vc_deal(vc_id, deal_id, approve=True)
    assert fund["ok"]
    assert fund["deal"]["status"] == "funded"
    assert w.companies[co_id].vc_raised_cents == 5_000_000
    assert w.ledger.total_money() == before
    w.assert_invariants()


def test_list_and_trade_conserves_money():
    w = World.from_config_path(CONFIG, seed=3)
    before = w.ledger.total_money()
    w.authority.create_company("alice", "Northstar Labs")
    co_id = w.agents["alice"].founded_company_id
    # capital so company is real
    w.authority.apply_loan("alice", 1_000_000, "cap")
    pitch = w.authority.pitch_to_vc("alice", co_id, 2_000_000, "ipo prep")
    w.authority.decide_vc_deal(pitch["deal"]["vc_agent_id"], pitch["deal"]["id"], True)
    listed = w.authority.list_company("alice", co_id, "NSTR", 1000)
    assert listed["ok"]
    # trader buys
    buy = w.authority.place_order("jake", "NSTR", "buy", 10, 1000)
    assert buy["ok"]
    trades = w.authority.clear_equity_markets()
    assert isinstance(trades, list)
    assert w.ledger.total_money() == before
    w.assert_invariants()


def test_thirty_day_rule_sim():
    orch = SimulationOrchestrator(CONFIG, seed=42, use_llm=False)
    state = orch.step(30)
    assert state["tick"] == 30
    orch.world.assert_invariants()
    m = state["metrics"]
    assert m["agent_count"] >= 20
    assert m["companies"] >= 1
    assert m["news_count"] >= 1
    # reflections should appear
    reflected = sum(1 for a in state["agents"] if a.get("reflection_count", 0) > 0)
    assert reflected >= 5
