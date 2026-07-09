"""World state + World Authority — sole mutator of economic state."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Optional, Union

import yaml

from .ledger import Ledger, LedgerError
from .markets import OrderBook, OrderSide
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
    VCDeal,
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
        sector = "tech"
        if "oil" in name.lower() or "energy" in name.lower():
            sector = "energy"
        elif "pay" in name.lower() or "bank" in name.lower():
            sector = "fintech"
        company = Company(
            id=company_id,
            name=name,
            founder_id=founder_id,
            cash_account_id=cash_acc.id,
            sector=sector,
            shares_issued=800_000,
            stage="seed",
        )
        # Founder gets initial equity allocation (book entry; cash already paid fee)
        w.market.add_shares(founder_id, f"PREIPO:{company_id}", 800_000)
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
            if not getattr(agent, "alive", True):
                emp.active = False
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
        energy = float(w.config.get("markets", {}).get("energy_price_index", 100.0))
        buyers = [
            a
            for a in w.agents.values()
            if getattr(a, "alive", True)
            and a.role
            in ("worker", "journalist", "lawyer", "banker", "entrepreneur", "trader", "vc")
        ]
        for co in w.companies.values():
            if co.inventory_units <= 0 or co.status != CompanyStatus.ACTIVE:
                continue
            price = co.product_price_cents
            if co.sector != "energy":
                price = int(price * (0.85 + 0.15 * (energy / 100.0)))
            else:
                price = int(co.product_price_cents * (energy / 100.0))
            for buyer in buyers:
                if co.inventory_units <= 0:
                    break
                bal = w.ledger.get(buyer.cash_account_id).balance_cents
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
                # opinion drift from news
                a.opinion_economy = max(
                    -1.0, min(1.0, a.opinion_economy * 0.9 + item.sentiment * 0.15)
                )
        return {"ok": True, "news": item.to_dict()}

    def pitch_to_vc(
        self,
        founder_id: str,
        company_id: str,
        amount_cents: int,
        pitch_note: str = "",
        vc_agent_id: Optional[str] = None,
    ) -> Result:
        w = self.w
        if founder_id not in w.agents or company_id not in w.companies:
            return Reject("unknown founder or company")
        co = w.companies[company_id]
        if co.founder_id != founder_id:
            return Reject("only founder can pitch")
        if amount_cents <= 0:
            return Reject("invalid amount")
        vc = None
        if vc_agent_id and vc_agent_id in w.agents and w.agents[vc_agent_id].role == "vc":
            vc = w.agents[vc_agent_id]
        else:
            vc = next((a for a in w.agents.values() if a.role == "vc"), None)
        if not vc:
            return Reject("no VC in world")

        # equity: 15% of post-money authorized float for seed, shares from unissued
        equity_pct = float(w.config.get("policy", {}).get("vc_equity_pct", 0.15))
        equity_shares = int(co.shares_authorized * equity_pct)
        remaining_room = co.shares_authorized - co.shares_issued
        equity_shares = max(1, min(equity_shares, remaining_room)) if remaining_room > 0 else max(1, equity_shares // 4)

        deal = VCDeal(
            id=new_id("vc_"),
            tick=w.tick,
            company_id=company_id,
            founder_id=founder_id,
            vc_agent_id=vc.id,
            amount_cents=amount_cents,
            equity_shares=equity_shares,
            status="pitched",
            pitch_note=pitch_note[:500],
        )
        w.vc_deals[deal.id] = deal
        w.emit("vc_pitch", f"{w.agents[founder_id].name} pitched {co.name} to {vc.name}", deal.to_dict())
        founder = w.agents[founder_id]
        founder.remember(w.tick, f"Pitched {co.name} to VC {vc.name} for ${amount_cents/100:.0f}", 0.85)
        vc.remember(w.tick, f"Received pitch from {founder.name}: {pitch_note[:120]}", 0.7)
        return {"ok": True, "deal": deal.to_dict()}

    def decide_vc_deal(self, vc_agent_id: str, deal_id: str, approve: bool = True) -> Result:
        w = self.w
        if deal_id not in w.vc_deals:
            return Reject("unknown deal")
        deal = w.vc_deals[deal_id]
        if deal.vc_agent_id != vc_agent_id:
            return Reject("not your deal")
        if deal.status != "pitched":
            return Reject("deal not in pitched state")
        if not approve:
            deal.status = "rejected"
            w.emit("vc_rejected", f"VC rejected deal {deal_id}", deal.to_dict())
            return {"ok": True, "deal": deal.to_dict()}

        vc = w.agents[vc_agent_id]
        co = w.companies[deal.company_id]
        vc_inst = w.institutions.get("vc")
        # Fund from VC firm capital if present else VC personal cash
        source_acc = vc_inst["cash_account_id"] if vc_inst else vc.cash_account_id
        try:
            w.ledger.transfer(
                source_acc,
                co.cash_account_id,
                deal.amount_cents,
                w.tick,
                f"VC funding {co.name}",
                ref=deal.id,
            )
        except LedgerError as e:
            deal.status = "rejected"
            return Reject(str(e))

        # Issue equity to VC (convert preipo founder symbol if needed)
        pre = f"PREIPO:{co.id}"
        # Dilution model: issue new shares to VC
        if co.shares_issued + deal.equity_shares <= co.shares_authorized:
            co.shares_issued += deal.equity_shares
        symbol = co.listed_symbol or pre
        w.market.add_shares(vc_agent_id, symbol, deal.equity_shares)
        co.vc_raised_cents += deal.amount_cents
        co.stage = "growth" if co.vc_raised_cents > 0 else co.stage
        deal.status = "funded"
        w.emit(
            "vc_funded",
            f"VC funded {co.name} with ${deal.amount_cents/100:,.0f}",
            deal.to_dict(),
        )
        w.agents[deal.founder_id].remember(
            w.tick, f"Raised ${deal.amount_cents/100:.0f} VC for {co.name}", 0.95
        )
        vc.remember(w.tick, f"Funded {co.name}; received {deal.equity_shares} shares", 0.9)
        return {"ok": True, "deal": deal.to_dict()}

    def list_company(self, founder_id: str, company_id: str, symbol: str, ipo_price_cents: int = 1000) -> Result:
        w = self.w
        if company_id not in w.companies:
            return Reject("unknown company")
        co = w.companies[company_id]
        if co.founder_id != founder_id:
            return Reject("only founder can list")
        if co.listed_symbol:
            return Reject("already listed")
        symbol = symbol.upper().replace(" ", "")[:8]
        if not symbol:
            return Reject("bad symbol")
        if symbol in w.market.listings:
            return Reject("symbol taken")
        if co.stage not in ("growth", "seed") or co.shares_issued < 1000:
            # allow seed list for Phase 1 demo after any capital
            pass
        float_shares = min(200_000, max(10_000, co.shares_issued // 5))
        # Move founder PREIPO holdings to listed symbol
        pre = f"PREIPO:{co.id}"
        founder_pre = w.market.get_holding(founder_id, pre)
        if founder_pre > 0:
            w.market.set_holding(founder_id, pre, 0)
            w.market.add_shares(founder_id, symbol, founder_pre)
        # any other PREIPO holders
        for (aid, sym), qty in list(w.market.holdings.items()):
            if sym == pre and qty > 0:
                w.market.set_holding(aid, pre, 0)
                w.market.add_shares(aid, symbol, qty)

        from .markets import Listing

        listing = Listing(
            symbol=symbol,
            company_id=co.id,
            shares_outstanding=co.shares_issued,
            last_price_cents=ipo_price_cents,
            listed_tick=w.tick,
            float_shares=float_shares,
        )
        w.market.listings[symbol] = listing
        co.listed_symbol = symbol
        co.stage = "public"
        # Founder posts initial sell of part of float to seed market
        seed_sell = min(float_shares // 2, w.market.get_holding(founder_id, symbol))
        if seed_sell > 0:
            w.market.place(w.tick, founder_id, symbol, OrderSide.SELL, seed_sell, ipo_price_cents)
        w.emit(
            "ipo",
            f"{co.name} listed as {symbol} @ ${ipo_price_cents/100:.2f}",
            listing.to_dict(),
        )
        w.agents[founder_id].remember(w.tick, f"Listed {co.name} as {symbol}", 0.95)
        return {"ok": True, "listing": listing.to_dict()}

    def place_order(
        self,
        agent_id: str,
        symbol: str,
        side: str,
        qty: int,
        price_cents: int,
    ) -> Result:
        w = self.w
        if agent_id not in w.agents:
            return Reject("unknown agent")
        if symbol not in w.market.listings:
            return Reject("unknown symbol")
        if qty <= 0 or price_cents <= 0:
            return Reject("invalid qty/price")
        side_e = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        if side_e == OrderSide.SELL:
            held = w.market.get_holding(agent_id, symbol)
            # count open sell residual
            open_sell = sum(
                o.qty - o.filled_qty
                for o in w.market.open_orders(symbol)
                if o.agent_id == agent_id and o.side == OrderSide.SELL
            )
            if held - open_sell < qty:
                return Reject("insufficient shares")
        else:
            # soft cash check
            need = qty * price_cents
            cash = w.ledger.get(w.agents[agent_id].cash_account_id).balance_cents
            if cash < need:
                return Reject("insufficient cash for buy order")
        order = w.market.place(w.tick, agent_id, symbol, side_e, qty, price_cents)
        w.emit("order", f"{agent_id} {side} {qty} {symbol} @ {price_cents}", order.to_dict())
        return {"ok": True, "order": order.to_dict()}

    def clear_equity_markets(self) -> list[dict[str, Any]]:
        """Match orders and settle cash + shares. Money conserved."""
        w = self.w
        trades = w.market.match_all(w.tick)
        settled = []
        for t in trades:
            buyer = w.agents.get(t.buyer_id)
            seller = w.agents.get(t.seller_id)
            if not buyer or not seller:
                continue
            notional = t.price_cents * t.qty
            try:
                w.ledger.transfer(
                    buyer.cash_account_id,
                    seller.cash_account_id,
                    notional,
                    w.tick,
                    f"Trade {t.symbol} x{t.qty}",
                    ref=t.id,
                )
            except LedgerError as e:
                w.emit("trade_fail", f"Settle failed {t.id}: {e}", t.to_dict())
                continue
            # share transfer
            if w.market.get_holding(t.seller_id, t.symbol) < t.qty:
                # rollback cash
                try:
                    w.ledger.transfer(
                        seller.cash_account_id,
                        buyer.cash_account_id,
                        notional,
                        w.tick,
                        f"Rollback trade {t.id}",
                        ref=t.id,
                    )
                except LedgerError:
                    pass
                continue
            w.market.add_shares(t.seller_id, t.symbol, -t.qty)
            w.market.add_shares(t.buyer_id, t.symbol, t.qty)
            settled.append(t.to_dict())
            w.emit(
                "trade",
                f"{t.qty} {t.symbol} @ ${t.price_cents/100:.2f}",
                t.to_dict(),
            )
            w.metrics["trades_today"] = w.metrics.get("trades_today", 0) + 1
            w.metrics["trade_notional_cents_today"] = (
                w.metrics.get("trade_notional_cents_today", 0) + notional
            )
        return settled

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
        elif shock_type == "energy_spike":
            pct = float(params.get("pct", 40))
            markets = w.config.setdefault("markets", {})
            old_e = float(markets.get("energy_price_index", 100.0))
            markets["energy_price_index"] = old_e * (1.0 + pct / 100.0)
            w.emit(
                "shock",
                f"Energy price index {old_e:.1f}→{markets['energy_price_index']:.1f} (+{pct}%)",
                shock.to_dict(),
            )
        elif shock_type == "energy_drop":
            pct = float(params.get("pct", 20))
            markets = w.config.setdefault("markets", {})
            old_e = float(markets.get("energy_price_index", 100.0))
            markets["energy_price_index"] = max(20.0, old_e * (1.0 - pct / 100.0))
            w.emit(
                "shock",
                f"Energy price index {old_e:.1f}→{markets['energy_price_index']:.1f} (-{pct}%)",
                shock.to_dict(),
            )
        elif shock_type == "cash_grant":
            amount = int(params.get("amount_cents", 100000))
            # Mint from fed settlement if present; else skip conservation-breaking
            fed = w.institutions.get("fed")
            if not fed:
                return Reject("no fed for grant")
            for a in w.agents.values():
                if not getattr(a, "alive", True):
                    continue
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
        self.vc_deals: dict[str, VCDeal] = {}
        self.market = OrderBook()
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
        seed_val = seed if seed is not None else int(config.get("seed", 42))
        from .population import expand_config_agents

        config = expand_config_agents(config, seed_val)
        world = cls(config, seed=seed_val)
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

        # VC firm capital pool
        vc_cfg = cfg.get("institutions", {}).get("vc")
        if vc_cfg:
            vc_cash = self.ledger.create_account(
                "institution",
                vc_cfg["id"],
                f"{vc_cfg['name']} Fund",
                int(endowments.get("vc_capital", 50_000_000)),
            )
            self.institutions["vc"] = {
                "id": vc_cfg["id"],
                "name": vc_cfg["name"],
                "cash_account_id": vc_cash.id,
            }

        # Treasury / government
        treas_cfg = cfg.get("institutions", {}).get("treasury")
        if treas_cfg:
            t_cash = self.ledger.create_account(
                "institution",
                treas_cfg["id"],
                f"{treas_cfg['name']} Treasury",
                int(endowments.get("treasury_capital", 200_000_000)),
            )
            self.institutions["treasury"] = {
                "id": treas_cfg["id"],
                "name": treas_cfg["name"],
                "cash_account_id": t_cash.id,
            }

        # Markets defaults
        self.config.setdefault("markets", {})
        self.config["markets"].setdefault("energy_price_index", 100.0)
        self.config.setdefault("politics", {"ruling_bloc": "center"})

        role_goals = {
            "entrepreneur": ["found a company", "raise capital", "hire talent", "grow revenue", "consider IPO"],
            "worker": ["find a good job", "earn wages", "stay healthy", "maybe invest savings"],
            "journalist": ["report on the economy", "publish daily news", "cover markets & VC"],
            "lawyer": ["help clients incorporate", "earn fees"],
            "banker": ["underwrite sound loans", "protect bank capital"],
            "vc": ["source deals", "fund winners", "build portfolio"],
            "trader": ["trade listed equities", "manage risk", "react to news"],
            "economist": ["track macro indicators", "advise research notes"],
            "politician": ["read public mood", "comment on policy"],
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
                company_name_pref=str(adef.get("company_name", "")),
                age=int(adef.get("age", 35)),
                sector_pref=str(adef.get("sector_pref", "tech")),
                alive=True,
            )
            agent.goals = list(role_goals.get(role, ["survive", "prosper"]))
            self.agents[agent.id] = agent

        self.ledger.freeze_initial_sum()
        self.emit("seed", f"World seeded with {len(self.agents)} agents", {"seed": self.seed})
        self.snapshot_metrics()

    def process_health(self) -> None:
        rate = float(self.config["policy"]["illness_rate"])
        dmin = int(self.config["policy"]["sick_days_min"])
        dmax = int(self.config["policy"]["sick_days_max"])
        for agent in self.agents.values():
            if not getattr(agent, "alive", True):
                continue
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
        from .macro import compute_macro

        unemployed = sum(
            1
            for a in self.agents.values()
            if a.role == "worker" and getattr(a, "alive", True) and not a.employer_company_id
        )
        workers = sum(1 for a in self.agents.values() if a.role == "worker" and getattr(a, "alive", True))
        sick = sum(1 for a in self.agents.values() if getattr(a, "alive", True) and a.health == HealthStatus.SICK)
        loans_out = sum(l.remaining_cents for l in self.loans.values() if l.status == LoanStatus.ACTIVE)
        agent_cash = sum(
            self.ledger.get(a.cash_account_id).balance_cents
            for a in self.agents.values()
            if getattr(a, "alive", True)
        )
        company_cash = sum(
            self.ledger.get(c.cash_account_id).balance_cents for c in self.companies.values()
        )
        inventory = sum(c.inventory_units for c in self.companies.values())
        vc_funded = sum(1 for d in self.vc_deals.values() if d.status == "funded")
        listings = list(self.market.listings.values())
        index = 0
        if listings:
            index = int(sum(L.last_price_cents for L in listings) / len(listings))
        base = {
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
            "agent_count": len(self.agents),
            "vc_deals": len(self.vc_deals),
            "vc_funded": vc_funded,
            "listings": len(listings),
            "equity_index_cents": index,
            "trades_today": self.metrics.get("trades_today", 0),
            "trade_notional_cents_today": self.metrics.get("trade_notional_cents_today", 0),
            "ruling_bloc": (self.config.get("politics") or {}).get("ruling_bloc", "center"),
        }
        self.metrics = base
        macro = compute_macro(self)
        base.update(macro)
        base["employed_workers"] = macro.get("employed_workers", base["employed_workers"])
        base["unemployed_workers"] = macro.get("unemployed_workers", base["unemployed_workers"])
        base["equity_index_cents"] = macro.get("equity_index_cents", index)
        base["avg_opinion_economy"] = macro.get("avg_opinion_economy", 0.0)
        self.metrics = base
        self.metrics_history.append(dict(base))
        return base

    def assert_invariants(self) -> None:
        self.ledger.assert_balanced()

    def public_state(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "paused": self.paused,
            "seed": self.seed,
            "phase": self.config.get("phase", "1"),
            "politics": self.config.get("politics", {}),
            "markets_cfg": self.config.get("markets", {}),
            "metrics": self.metrics,
            "agents": [
                a.to_public_dict()
                | {"cash_cents": self.ledger.get(a.cash_account_id).balance_cents}
                for a in self.agents.values()
            ],
            "companies": [
                c.to_dict() | {"cash_cents": self.ledger.get(c.cash_account_id).balance_cents}
                for c in self.companies.values()
            ],
            "loans": [l.to_dict() for l in self.loans.values()],
            "jobs": [j.to_dict() for j in self.job_postings.values()],
            "vc_deals": [d.to_dict() for d in self.vc_deals.values()],
            "market": self.market.book_snapshot(),
            "accounts": self.ledger.balances_public(),
            "news": [n.to_dict() for n in self.news[-50:]],
            "events": [e.to_dict() for e in self.events[-100:]],
            "institutions": {
                k: {kk: vv for kk, vv in v.items() if kk != "cash_account_id"}
                | {"cash_cents": self.ledger.get(v["cash_account_id"]).balance_cents}
                for k, v in self.institutions.items()
            },
        }
