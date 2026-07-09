from pathlib import Path

from backend.engine.models import HealthStatus
from backend.engine.world import World
from backend.agents.orchestrator import SimulationOrchestrator

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "baseline_csus.yaml"


def test_hire_and_payroll():
    w = World.from_config_path(CONFIG, seed=11)
    # setup company + capital
    w.authority.create_company("alice", "PayCo")
    co = w.companies[w.agents["alice"].founded_company_id]
    w.authority.apply_loan("alice", 2_000_000, "fund")
    w.authority.transfer(
        w.agents["alice"].cash_account_id,
        co.cash_account_id,
        1_000_000,
        "cap",
    )
    post = w.authority.post_job(co.id, "Engineer", 15000)
    assert post["ok"]
    pid = post["posting"]["id"]
    w.authority.apply_job("dave", pid)
    hired = w.authority.hire(co.id, "dave", pid)
    assert hired["ok"]

    before_dave = w.ledger.get(w.agents["dave"].cash_account_id).balance_cents
    before_total = w.ledger.total_money()
    results = w.authority.run_payroll_and_production()
    assert any(r.get("paid") for r in results)
    after_dave = w.ledger.get(w.agents["dave"].cash_account_id).balance_cents
    assert after_dave == before_dave + 15000
    assert w.ledger.total_money() == before_total
    assert co.inventory_units >= 2


def test_sickness_skips_payroll():
    w = World.from_config_path(CONFIG, seed=12)
    w.authority.create_company("alice", "SickCo")
    co = w.companies[w.agents["alice"].founded_company_id]
    w.authority.apply_loan("alice", 2_000_000, "fund")
    w.authority.transfer(w.agents["alice"].cash_account_id, co.cash_account_id, 1_000_000, "cap")
    post = w.authority.post_job(co.id, "Ops", 14000)
    pid = post["posting"]["id"]
    w.authority.apply_job("erin", pid)
    w.authority.hire(co.id, "erin", pid)
    w.agents["erin"].health = HealthStatus.SICK
    w.agents["erin"].sick_days_remaining = 2
    before = w.ledger.get(w.agents["erin"].cash_account_id).balance_cents
    results = w.authority.run_payroll_and_production()
    assert any(r.get("reason") == "sick" for r in results)
    assert w.ledger.get(w.agents["erin"].cash_account_id).balance_cents == before


def test_fourteen_day_rule_sim():
    orch = SimulationOrchestrator(CONFIG, seed=42, use_llm=False)
    state = orch.step(14)
    assert state["tick"] == 14
    orch.world.assert_invariants()
    # founder path should produce a company under rule policy
    assert state["metrics"]["companies"] >= 1
    assert state["metrics"]["news_count"] >= 1
