from pathlib import Path

from backend.engine.world import World

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "baseline_csus.yaml"


def test_loan_disbursement_balances():
    w = World.from_config_path(CONFIG, seed=7)
    before = w.ledger.total_money()
    alice = w.agents["alice"]
    personal_before = w.ledger.get(alice.cash_account_id).balance_cents
    bank_before = w.ledger.get(w.institutions["bank"]["cash_account_id"]).balance_cents

    result = w.authority.apply_loan(alice.id, 1_000_000, purpose="test")
    assert result["ok"] is True
    loan = result["loan"]
    assert loan["status"] == "active"
    assert loan["principal_cents"] > 0

    personal_after = w.ledger.get(alice.cash_account_id).balance_cents
    bank_after = w.ledger.get(w.institutions["bank"]["cash_account_id"]).balance_cents
    assert personal_after == personal_before + loan["principal_cents"]
    assert bank_after == bank_before - loan["principal_cents"]
    assert w.ledger.total_money() == before
    w.assert_invariants()


def test_company_creation_pays_lawyer():
    w = World.from_config_path(CONFIG, seed=3)
    before = w.ledger.total_money()
    alice = w.agents["alice"]
    bob = w.agents["bob"]
    fee = int(w.config["policy"]["incorporation_fee_cents"])
    bob_before = w.ledger.get(bob.cash_account_id).balance_cents

    result = w.authority.create_company(alice.id, "TestCo")
    assert result["ok"] is True
    assert alice.founded_company_id in w.companies
    assert w.ledger.get(bob.cash_account_id).balance_cents == bob_before + fee
    assert w.ledger.total_money() == before
    w.assert_invariants()
