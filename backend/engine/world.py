"""World state + World Authority — sole mutator of economic state."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Optional, Union

import yaml

from .ledger import Ledger, LedgerError
from .models import (
    Agent,
    Company,
    CompanyStatus,
    Employment,
    Event,
    HealthStatus,
    JobPosting,
    Loan,
    LoanStatus,
    NewsItem,
    Persona,
    Reject,
    ShockEvent,
    new_id,
)


Result = Union[dict[str, Any], Reject]


class WorldAuthority:
    """Validates and executes all agent-proposed actions."""

    def __init__(self, world: "World") -> None:
        self.w = world

    # ---- money ----
    def transfer(
        self,
        debit_account_id: str,
        credit_account_id: str,
        amount_cents: int,
        memo: str,
        ref: Optional[str] = None,
        allow_overdraft: bool = False,
    ) -> Result:
        try:
            tx = self.w.ledger.transfer(
                debit_account_id,
                credit_account_id,
                amount_cents,
                self.w.tick,
                memo,
                ref=ref,
                allow_overdraft=allow_overdraft,
            )
            self.w.emit("transfer", memo, tx.to_dict())
            return {"ok": True, "transaction": tx.to_dict()}
        except LedgerError as e:
            return Reject(str(e))

    def create_company(self, founder_id: str, name: str) -> Result:
        w = self.w
        if founder_id not in w.agents:
            return Reject("unknown founder")
        founder = w.agents[founder_id]
        if founder.founded_company_id:
            return Reject("founder already has a company")
        fee = int(w.config["policy"]["incorporation_fee_cents"])
        lawyer = next((a for a in w.agents.values() if a.role == "lawyer"), None)
        if not lawyer:
            return Reject("no lawyer in world")
        if w.ledger.get(founder.cash_account_id).balance_cents < fee:
            return Reject("insufficient funds for incorporation fee")

        company_id = new_id("co_")
        cash_acc = w.ledger.create_account("company", company_id, f"{name} Cash", 0)
        company = Company(
            id=company_id,
            name=name,
            founder_id=founder_id,
            cash_account_id=cash_acc.id,
        )
        # Pay lawyer fee
        try:
            w.ledger.transfer(
                founder.cash_account_id,
                lawyer.cash_account_id,
                fee,
                w.tick,
                f"Incorporation fee for {name}",
                ref=company_id,
            )
        except LedgerError as e:
            return Reject(str(e))

        w.companies[company_id] = company
        founder.founded_company_id = company_id
        founder.remember(w.tick, f"Founded company {name}", importance=0.9)
        lawyer.remember(w.tick, f"Incorporated {name} for {founder.name}, earned fee", importance=0.7)
        w.emit(
            "company_created",
            f"{founder.name} founded {name}",
            {"company_id": company_id, "founder_id": founder_id, "fee_cents": fee},
        )
        return {"ok": True, "company": company.to_dict(), "fee_cents": fee}

    def apply_loan(
        self,
        borrower_id: str,
        amount_cents: int,
        purpose: str = "",
        borrower_type: str = "agent",
    ) -> Result:
        w = self.w
        bank = w.institutions.get("bank")
        if not bank:
            return Reject("no bank")
        if amount_cents <= 0:
            return Reject("invalid amount")

        bank_cash_id = bank["cash_account_id"]
        bank_cash = w.ledger.get(bank_cash_id).balance_cents
        cap = float(w.config["policy"]["bank_reserve_loan_cap"])
        max_lend = int(bank_cash * cap)

        if borrower_type == "agent":
            if borrower_id not in w.agents:
                return Reject("unknown borrower")
            borrower_acc = w.agents[borrower_id].cash_account_id
            endowment = w.ledger.get(borrower_acc).balance_cents
        elif borrower_type == "company":
            if borrower_id not in w.companies:
                return Reject("unknown company")
            co = w.companies[borrower_id]
            borrower_acc = co.cash_account_id
            founder = w.agents[co.founder_id]
            endowment = w.ledger.get(founder.cash_account_id).balance_cents + w.ledger.get(
                borrower_acc
            ).balance_cents
        else:
            return Reject("invalid borrower_type")

        max_by_endowment = int(endowment * float(w.config["policy"]["max_loan_to_endowment"]))
        approved_amount = min(amount_cents, max_lend, max_by_endowment)

        loan = Loan(
            id=new_id("loan_"),
            bank_id=bank["id"],
            borrower_type=borrower_type,
            borrower_id=borrower_id,
            principal_cents=amount_cents,
            remaining_cents=0,
            rate_bps=int(w.config["policy"]["policy_rate_bps"]) + 300,
            status=LoanStatus.PENDING,
            purpose=purpose,
            tick_origin=w.tick,
        )

        if approved_amount < max(amount_cents // 4, 10000):
            loan.status = LoanStatus.REJECTED
            w.loans[loan.id] = loan
            w.emit("loan_rejected", f"Loan rejected for {borrower_id}", loan.to_dict())
            return Reject(f"loan rejected; max approvable ~{approved_amount}")

        try:
            w.ledger.transfer(
                bank_cash_id,
                borrower_acc,
                approved_amount,
                w.tick,
                f"Loan disbursement {loan.id}",
                ref=loan.id,
            )
        except LedgerError as e:
            loan.status = LoanStatus.REJECTED
            w.loans[loan.id] = loan
            return Reject(str(e))

        loan.principal_cents = approved_amount
        loan.remaining_cents = approved_amount
        loan.status = LoanStatus.ACTIVE
        w.loans[loan.id] = loan
        w.emit(
            "loan_approved",
            f"Loan {approved_amount/100:.2f} USD to {borrower_id}",
            loan.to_dict(),
        )
        if borrower_type == "agent":
            w.agents[borrower_id].remember(
                w.tick, f"Received loan of ${approved_amount/100:.2f} for {purpose}", 0.85
            )
        return {"ok": True, "loan": loan.to_dict()}

    def post_job(self, company_id: str, title: str, wage_cents_day: int) -> Result:
        w = self.w
        if company_id not in w.companies:
            return Reject("unknown company")
        co = w.companies[company_id]
        if co.status != CompanyStatus.ACTIVE:
            return Reject("company not active")
        min_w = int(w.config["policy"]["min_wage_cents_day"])
        if wage_cents_day < min_w:
            return Reject(f"wage below minimum {min_w}")
        posting = JobPosting(
            id=new_id("job_"),
            company_id=company_id,
            title=title,
            wage_cents_day=wage_cents_day,
        )
        w.job_postings[posting.id] = posting
        w.emit("job_posted", f"{co.name} posted {title} @ ${wage_cents_day/100:.0f}/day", posting.to_dict())
        return {"ok": True, "posting": posting.to_dict()}

    def apply_job(self, agent_id: str, posting_id: str) -> Result:
        w = self.w
        if agent_id not in w.agents:
            return Reject("unknown agent")
        if posting_id not in w.job_postings:
            return Reject("unknown posting")
        agent = w.agents[agent_id]
        posting = w.job_postings[posting_id]
        if not posting.open:
            return Reject("posting closed")
        if agent.employer_company_id:
            return Reject("already employed")
        if agent_id not in posting.applicants:
            posting.applicants.append(agent_id)
        agent.remember(w.tick, f"Applied to job {posting.title}", 0.5)
        w.emit("job_applied", f"{agent.name} applied to {posting.title}", {"agent_id": agent_id, "posting_id": posting_id})
        return {"ok": True, "posting": posting.to_dict()}

    def hire(self, company_id: str, agent_id: str, posting_id: str) -> Result:
        w = self.w
        if company_id not in w.companies:
            return Reject("unknown company")
        if agent_id not in w.agents:
            return Reject("unknown agent")
        if posting_id not in w.job_postings:
            return Reject("unknown posting")
        posting = w.job_postings[posting_id]
        agent = w.agents[agent_id]
        if posting.company_id != company_id:
            return Reject("posting/company mismatch")
        if not posting.open:
            return Reject("posting closed")
        if agent.employer_company_id:
            return Reject("agent already employed")

        emp = Employment(
            agent_id=agent_id,
            company_id=company_id,
            wage_cents_day=posting.wage_cents_day,
            posting_id=posting_id,
        )
        w.employments[agent_id] = emp
        agent.employer_company_id = company_id
        posting.open = False
        agent.remember(w.tick, f"Hired by company {company_id} as {posting.title}", 0.8)
        w.emit(
            "hired",
            f"{agent.name} hired @ ${posting.wage_cents_day/100:.0f}/day",
            emp.to_dict(),
        )
        return {"ok": True, "employment": emp.to_dict()}

    def run_payroll_and_production(self) -> list[dict[str, Any]]:
        """Pay healthy workers and add inventory."""
        w = self.w
        results = []
        for emp in list(w.employments.values()):
            if not emp.active:
                continue
            agent = w.agents[emp.agent_id]
            company = w.companies.get(emp.company_id)
            if not company or company.status != CompanyStatus.ACTIVE:
                continue
            if agent.health != HealthStatus.HEALTHY:
                w.emit("sick_day", f"{agent.name} missed work (sick)", {"agent_id": agent.id})
                agent.remember(w.tick, "Missed work due to illness", 0.6)
                results.append({"agent_id": agent.id, "paid": False, "reason": "sick"})
                continue
            try:
                tx = w.ledger.transfer(
                    company.cash_account_id,
                    agent.cash_account_id,
                    emp.wage_cents_day,
                    w.tick,
                    f"Payroll {agent.name}",
                    ref=emp.company_id,
                )
                company.inventory_units += company.daily_productivity_per_worker
                w.metrics["production_units_today"] = w.metrics.get("production_units_today", 0) + company.daily_productivity_per_worker
                results.append({"agent_id": agent.id, "paid": True, "tx": tx.to_dict()})
            except LedgerError as e:
                w.emit("payroll_failed", f"Payroll failed for {agent.name}: {e}", {})
                results.append({"agent_id": agent.id, "paid": False, "reason": str(e)})
        return results

    def sell_goods_simple(self) -> None:
        """Consumers with cash buy from companies with inventory (simple clearing)."""
        w = self.w
        buyers = [a for a in w.agents.values() if a.role in ("worker", "journalist", "lawyer", "banker", "entrepreneur")]
        for co in w.companies.values():
            if co.inventory_units <= 0 or co.status != CompanyStatus.ACTIVE:
                continue
            price = co.product_price_cents
            for buyer in buyers:
                if co.inventory_units <= 0:
                    break
                bal = w.ledger.get(buyer.cash_account_id).balance_cents
                # spend up to 5% of cash or 1 unit
                if bal < price:
                    continue
                if w.rng.random() > 0.35:
                    continue
                try:
                    w.ledger.transfer(
                        buyer.cash_account_id,
                        co.cash_account_id,
                        price,
                        w.tick,
                        f"Purchase from {co.name}",
                        ref=co.id,
                    )
                    co.inventory_units -= 1
                    w.metrics["sales_today"] = w.metrics.get("sales_today", 0) + 1
                    w.metrics["sales_cents_today"] = w.metrics.get("sales_cents_today", 0) + price
                except LedgerError:
                    continue

    def publish_news(self, author_id: str, headline: str, body: str, sentiment: float = 0.0) -> Result:
        w = self.w
        if author_id not in w.agents:
            return Reject("unknown author")
        item = NewsItem(
            id=new_id("news_"),
            tick=w.tick,
            author_id=author_id,
            headline=headline[:200],
            body=body[:2000],
            sentiment=max(-1.0, min(1.0, float(sentiment))),
        )
        w.news.append(item)
        w.emit("news", headline, item.to_dict())
        for a in w.agents.values():
            if a.id != author_id:
                a.remember(w.tick, f"News: {headline}", importance=0.4 + abs(item.sentiment) * 0.3)
        return {"ok": True, "news": item.to_dict()}

    def inject_shock(self, shock_type: str, params: Optional[dict[str, Any]] = None) -> Result:
        w = self.w
        params = params or {}
        shock = ShockEvent(tick=w.tick, type=shock_type, params=params)
        w.shocks.append(shock)

        if shock_type == "rate_hike":
            bps = int(params.get("bps", 50))
            w.config["policy"]["policy_rate_bps"] = int(w.config["policy"]["policy_rate_bps"]) + bps
            w.emit("shock", f"Policy rate +{bps} bps", shock.to_dict())
        elif shock_type == "rate_cut":
            bps = int(params.get("bps", 25))
            w.config["policy"]["policy_rate_bps"] = max(
                0, int(w.config["policy"]["policy_rate_bps"]) - bps
            )
            w.emit("shock", f"Policy rate -{bps} bps", shock.to_dict())
        elif shock_type == "illness_wave":
            rate = float(params.get("rate", 0.5))
            for a in w.agents.values():
                if a.health == HealthStatus.HEALTHY and w.rng.random() < rate:
                    a.health = HealthStatus.SICK
                    a.sick_days_remaining = int(params.get("days", 3))
            w.emit("shock", f"Illness wave rate={rate}", shock.to_dict())
        elif shock_type == "cash_grant":
            amount = int(params.get("amount_cents", 100000))
            # Mint from fed settlement if present; else skip conservation-breaking
            fed = w.institutions.get("fed")
            if not fed:
                return Reject("no fed for grant")
            for a in w.agents.values():
                try:
                    w.ledger.transfer(
                        fed["cash_account_id"],
                        a.cash_account_id,
                        amount,
                        w.tick,
                        "Stimulus grant",
                        allow_overdraft=True,
                    )
                except LedgerError:
                    pass
            # grants with overdraft change total money — re-freeze baseline
            w.ledger.freeze_initial_sum()
            w.emit("shock", f"Cash grant ${amount/100:.2f} each", shock.to_dict())
        else:
            w.emit("shock", f"Unknown shock {shock_type}", shock.to_dict())
            return Reject(f"unknown shock type {shock_type}")

        return {"ok": True, "shock": shock.to_dict()}


class World:
    def __init__(self, config: dict[str, Any], seed: Optional[int] = None) -> None:
        self.config = config
        self.seed = seed if seed is not None else int(config.get("seed", 42))
        self.rng = random.Random(self.seed)
        self.tick = 0
        self.paused = True
        self.ledger = Ledger()
        self.agents: dict[str, Agent] = {}
        self.companies: dict[str, Company] = {}
        self.loans: dict[str, Loan] = {}
        self.job_postings: dict[str, JobPosting] = {}
        self.employments: dict[str, Employment] = {}
        self.news: list[NewsItem] = []
        self.events: list[Event] = []
        self.shocks: list[ShockEvent] = []
        self.institutions: dict[str, dict[str, Any]] = {}
        self.metrics: dict[str, Any] = {}
        self.metrics_history: list[dict[str, Any]] = []
        self.authority = WorldAuthority(self)
        self._listeners: list = []

    @classmethod
    def from_config_path(cls, path: str | Path, seed: Optional[int] = None) -> "World":
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        world = cls(config, seed=seed)
        world.seed_from_config()
        return world

    def on_event(self, callback) -> None:
        self._listeners.append(callback)

    def emit(self, kind: str, message: str, data: Optional[dict] = None) -> None:
        ev = Event(tick=self.tick, kind=kind, message=message, data=data or {})
        self.events.append(ev)
        if len(self.events) > 5000:
            self.events = self.events[-5000:]
        for cb in self._listeners:
            try:
                cb(ev)
            except Exception:
                pass

    def seed_from_config(self) -> None:
        cfg = self.config
        endowments = cfg.get("endowments_cents", {})

        # Bank
        bank_cfg = cfg["institutions"]["bank"]
        bank_cash = self.ledger.create_account(
            "institution",
            bank_cfg["id"],
            f"{bank_cfg['name']} Cash",
            int(endowments.get("bank_capital", 0)),
        )
        self.institutions["bank"] = {
            "id": bank_cfg["id"],
            "name": bank_cfg["name"],
            "cash_account_id": bank_cash.id,
        }

        # Fed (for shocks / settlement)
        fed_cfg = cfg["institutions"]["fed"]
        fed_cash = self.ledger.create_account(
            "institution",
            fed_cfg["id"],
            f"{fed_cfg['name']} Settlement",
            int(endowments.get("fed_settlement", 0)),
        )
        self.institutions["fed"] = {
            "id": fed_cfg["id"],
            "name": fed_cfg["name"],
            "cash_account_id": fed_cash.id,
        }

        for adef in cfg.get("agents", []):
            role = adef["role"]
            end_key = role if role in endowments else "worker"
            cash = self.ledger.create_account(
                "agent",
                adef["id"],
                f"{adef['name']} Cash",
                int(endowments.get(end_key, 1_000_000)),
            )
            persona = Persona(
                political_lean=adef.get("political_lean", "center"),
                risk_tolerance=float(adef.get("risk_tolerance", 0.5)),
                skills=dict(adef.get("skills", {})),
                occupation=adef.get("occupation", role),
            )
            agent = Agent(
                id=adef["id"],
                name=adef["name"],
                role=role,
                persona=persona,
                cash_account_id=cash.id,
            )
            if role == "entrepreneur":
                agent.goals = ["found a company", "raise capital", "hire talent", "grow revenue"]
            elif role == "worker":
                agent.goals = ["find a good job", "earn wages", "stay healthy"]
            elif role == "journalist":
                agent.goals = ["report on the economy", "publish daily news"]
            elif role == "lawyer":
                agent.goals = ["help clients incorporate", "earn fees"]
            elif role == "banker":
                agent.goals = ["underwrite sound loans", "protect bank capital"]
            self.agents[agent.id] = agent

        self.ledger.freeze_initial_sum()
        self.emit("seed", f"World seeded with {len(self.agents)} agents", {"seed": self.seed})
        self.snapshot_metrics()

    def process_health(self) -> None:
        rate = float(self.config["policy"]["illness_rate"])
        dmin = int(self.config["policy"]["sick_days_min"])
        dmax = int(self.config["policy"]["sick_days_max"])
        for agent in self.agents.values():
            if agent.health == HealthStatus.SICK:
                agent.sick_days_remaining -= 1
                if agent.sick_days_remaining <= 0:
                    agent.health = HealthStatus.HEALTHY
                    agent.sick_days_remaining = 0
                    agent.remember(self.tick, "Recovered from illness", 0.5)
                    self.emit("recovered", f"{agent.name} recovered", {"agent_id": agent.id})
            elif self.rng.random() < rate:
                agent.health = HealthStatus.SICK
                agent.sick_days_remaining = self.rng.randint(dmin, dmax)
                agent.remember(self.tick, f"Fell ill for {agent.sick_days_remaining} days", 0.7)
                self.emit(
                    "fell_ill",
                    f"{agent.name} fell ill ({agent.sick_days_remaining}d)",
                    {"agent_id": agent.id},
                )

    def snapshot_metrics(self) -> dict[str, Any]:
        unemployed = sum(
            1
            for a in self.agents.values()
            if a.role == "worker" and not a.employer_company_id
        )
        workers = sum(1 for a in self.agents.values() if a.role == "worker")
        sick = sum(1 for a in self.agents.values() if a.health == HealthStatus.SICK)
        loans_out = sum(l.remaining_cents for l in self.loans.values() if l.status == LoanStatus.ACTIVE)
        agent_cash = sum(
            self.ledger.get(a.cash_account_id).balance_cents for a in self.agents.values()
        )
        company_cash = sum(
            self.ledger.get(c.cash_account_id).balance_cents for c in self.companies.values()
        )
        inventory = sum(c.inventory_units for c in self.companies.values())
        m = {
            "tick": self.tick,
            "seed": self.seed,
            "paused": self.paused,
            "policy_rate_bps": self.config["policy"]["policy_rate_bps"],
            "total_money_cents": self.ledger.total_money(),
            "agent_cash_cents": agent_cash,
            "company_cash_cents": company_cash,
            "loans_outstanding_cents": loans_out,
            "companies": len(self.companies),
            "open_jobs": sum(1 for j in self.job_postings.values() if j.open),
            "employed_workers": workers - unemployed,
            "unemployed_workers": unemployed,
            "sick_agents": sick,
            "inventory_units": inventory,
            "news_count": len(self.news),
            "production_units_today": self.metrics.get("production_units_today", 0),
            "sales_today": self.metrics.get("sales_today", 0),
            "sales_cents_today": self.metrics.get("sales_cents_today", 0),
        }
        self.metrics = m
        self.metrics_history.append(dict(m))
        return m

    def assert_invariants(self) -> None:
        self.ledger.assert_balanced()

    def public_state(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "paused": self.paused,
            "seed": self.seed,
            "metrics": self.metrics,
            "agents": [a.to_public_dict() | {"cash_cents": self.ledger.get(a.cash_account_id).balance_cents} for a in self.agents.values()],
            "companies": [c.to_dict() | {"cash_cents": self.ledger.get(c.cash_account_id).balance_cents} for c in self.companies.values()],
            "loans": [l.to_dict() for l in self.loans.values()],
            "jobs": [j.to_dict() for j in self.job_postings.values()],
            "accounts": self.ledger.balances_public(),
            "news": [n.to_dict() for n in self.news[-50:]],
            "events": [e.to_dict() for e in self.events[-100:]],
            "institutions": {
                k: {kk: vv for kk, vv in v.items() if kk != "cash_account_id"}
                | {"cash_cents": self.ledger.get(v["cash_account_id"]).balance_cents}
                for k, v in self.institutions.items()
            },
        }
