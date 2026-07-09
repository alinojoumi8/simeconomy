"""Double-entry ledger. Money is integer cents only."""

from __future__ import annotations

from typing import Optional

from .models import Account, Transaction, new_id


class LedgerError(Exception):
    pass


class Ledger:
    def __init__(self) -> None:
        self.accounts: dict[str, Account] = {}
        self.transactions: list[Transaction] = []
        self._initial_sum_cents: Optional[int] = None

    def create_account(
        self,
        owner_type: str,
        owner_id: str,
        name: str,
        opening_balance_cents: int = 0,
        account_id: Optional[str] = None,
    ) -> Account:
        acc = Account(
            id=account_id or new_id("acc_"),
            owner_type=owner_type,
            owner_id=owner_id,
            name=name,
            balance_cents=opening_balance_cents,
        )
        self.accounts[acc.id] = acc
        return acc

    def freeze_initial_sum(self) -> None:
        """Call after seeding endowments. Conservation checked against this total."""
        self._initial_sum_cents = self.total_money()

    def total_money(self) -> int:
        return sum(a.balance_cents for a in self.accounts.values())

    def get(self, account_id: str) -> Account:
        if account_id not in self.accounts:
            raise LedgerError(f"unknown account {account_id}")
        return self.accounts[account_id]

    def transfer(
        self,
        debit_account_id: str,
        credit_account_id: str,
        amount_cents: int,
        tick: int,
        memo: str,
        ref: Optional[str] = None,
        allow_overdraft: bool = False,
    ) -> Transaction:
        if amount_cents <= 0:
            raise LedgerError("amount must be positive")
        if debit_account_id == credit_account_id:
            raise LedgerError("debit and credit must differ")

        debit = self.get(debit_account_id)
        credit = self.get(credit_account_id)

        if not allow_overdraft and debit.balance_cents < amount_cents:
            raise LedgerError(
                f"insufficient funds in {debit.name}: have {debit.balance_cents}, need {amount_cents}"
            )

        debit.balance_cents -= amount_cents
        credit.balance_cents += amount_cents

        tx = Transaction(
            id=new_id("tx_"),
            tick=tick,
            debit_account_id=debit_account_id,
            credit_account_id=credit_account_id,
            amount_cents=amount_cents,
            memo=memo,
            ref=ref,
        )
        self.transactions.append(tx)
        return tx

    def assert_balanced(self) -> None:
        if self._initial_sum_cents is None:
            return
        total = self.total_money()
        if total != self._initial_sum_cents:
            raise LedgerError(
                f"ledger imbalance: total={total} expected={self._initial_sum_cents} "
                f"delta={total - self._initial_sum_cents}"
            )

    def balances_public(self) -> list[dict]:
        return [a.to_dict() for a in sorted(self.accounts.values(), key=lambda x: x.name)]
