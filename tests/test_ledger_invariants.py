from pathlib import Path

import pytest

from backend.engine.ledger import Ledger, LedgerError
from backend.engine.world import World

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "baseline_csus.yaml"


def test_transfer_preserves_total():
    led = Ledger()
    a = led.create_account("agent", "a", "A", 10000)
    b = led.create_account("agent", "b", "B", 5000)
    led.freeze_initial_sum()
    led.transfer(a.id, b.id, 2500, tick=1, memo="pay")
    assert led.total_money() == 15000
    led.assert_balanced()
    assert led.get(a.id).balance_cents == 7500
    assert led.get(b.id).balance_cents == 7500


def test_overdraft_rejected():
    led = Ledger()
    a = led.create_account("agent", "a", "A", 100)
    b = led.create_account("agent", "b", "B", 0)
    with pytest.raises(LedgerError):
        led.transfer(a.id, b.id, 200, tick=1, memo="too much")


def test_world_seed_balanced():
    w = World.from_config_path(CONFIG, seed=1)
    w.assert_invariants()
    assert len(w.agents) >= 20
    assert w.ledger.total_money() > 0
