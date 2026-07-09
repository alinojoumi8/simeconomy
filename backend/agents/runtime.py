"""Agent decision loop: LLM tools or rule policy → World Authority."""

from __future__ import annotations

from typing import Any, Optional

from backend.engine.models import Agent, HealthStatus
from backend.engine.world import World
from backend.llm.router import LLMRouter


class RulePolicy:
    """Deterministic persona scripts so Phase 1 runs without APIs."""

    def decide(self, world: World, agent: Agent) -> list[dict[str, Any]]:
        if not getattr(agent, "alive", True):
            return [{"tool": "noop", "args": {"reason": "deceased"}}]
        if agent.health == HealthStatus.SICK:
            return [{"tool": "noop", "args": {"reason": "sick"}}]

        role = agent.role
        tick = world.tick

        if role == "entrepreneur":
            return self._entrepreneur(world, agent, tick)
        if role == "worker":
            return self._worker(world, agent, tick)
        if role == "journalist":
            return self._journalist(world, agent, tick)
        if role == "lawyer":
            return [{"tool": "noop", "args": {"reason": "awaiting clients"}}]
        if role == "banker":
            return [{"tool": "noop", "args": {"reason": "monitoring portfolio"}}]
        if role == "vc":
            return self._vc(world, agent, tick)
        if role == "trader":
            return self._trader(world, agent, tick)
        if role == "economist":
            return self._economist(world, agent, tick)
        if role == "politician":
            return self._politician(world, agent, tick)
        return [{"tool": "noop", "args": {"reason": "no policy"}}]

    def _entrepreneur(self, world: World, agent: Agent, tick: int) -> list[dict[str, Any]]:
        name = agent.company_name_pref or (
            "Northstar Labs" if agent.id == "alice" else f"{agent.name.split()[0]} Ventures"
        )
        if not agent.founded_company_id:
            if tick >= 1:
                return [{"tool": "create_company", "args": {"name": name}}]
            return [{"tool": "noop", "args": {"reason": "planning venture"}}]

        co_id = agent.founded_company_id
        co = world.companies[co_id]
        co_cash = world.ledger.get(co.cash_account_id).balance_cents
        max_hires = 4 if agent.id == "alice" else 3

        has_loan = any(
            l.borrower_id in (agent.id, co_id) and l.status.value == "active"
            for l in world.loans.values()
        )
        if not has_loan and tick >= 2:
            return [
                {
                    "tool": "apply_loan",
                    "args": {
                        "amount_cents": 2_500_000 if agent.id == "alice" else 1_500_000,
                        "purpose": f"working capital for {co.name}",
                        "borrower_type": "agent",
                    },
                }
            ]

        personal = world.ledger.get(agent.cash_account_id).balance_cents
        if co_cash < 400_000 and personal > 800_000 and tick >= 3:
            return [
                {
                    "tool": "capitalize_company",
                    "args": {"company_id": co_id, "amount_cents": min(1_500_000, personal // 2)},
                }
            ]

        # VC pitch once after capital
        pitched = any(d.company_id == co_id for d in world.vc_deals.values())
        funded = any(d.company_id == co_id and d.status == "funded" for d in world.vc_deals.values())
        if not pitched and tick >= 6 and co_cash >= 200_000:
            return [
                {
                    "tool": "pitch_vc",
                    "args": {
                        "company_id": co_id,
                        "amount_cents": 5_000_000 if co.sector == "tech" else 3_000_000,
                        "pitch_note": f"{co.name} is scaling {co.sector} with inventory {co.inventory_units}",
                    },
                }
            ]

        open_for_co = [j for j in world.job_postings.values() if j.company_id == co_id and j.open]
        employed_here = [e for e in world.employments.values() if e.company_id == co_id and e.active]
        if not open_for_co and len(employed_here) < max_hires and co_cash >= 200_000 and tick >= 4:
            titles = [
                ("Software Engineer", 18000),
                ("Operations Associate", 14000),
                ("Sales Associate", 15000),
                ("Analyst", 16000),
            ]
            title, wage = titles[len(employed_here) % len(titles)]
            return [
                {
                    "tool": "post_job",
                    "args": {"company_id": co_id, "title": title, "wage_cents_day": wage},
                }
            ]

        for j in world.job_postings.values():
            if j.company_id == co_id and j.open and j.applicants:
                return [
                    {
                        "tool": "hire",
                        "args": {
                            "company_id": co_id,
                            "agent_id": j.applicants[0],
                            "posting_id": j.id,
                        },
                    }
                ]

        # IPO after funding + employees (inventory not required — may sell out same day)
        if (
            not co.listed_symbol
            and funded
            and len(employed_here) >= 1
            and co.vc_raised_cents > 0
            and tick >= 12
        ):
            symbol = "NSTR" if "Northstar" in co.name else co.name[:4].upper()
            return [
                {
                    "tool": "list_company",
                    "args": {
                        "company_id": co_id,
                        "symbol": symbol,
                        "ipo_price_cents": 1200 if funded else 800,
                    },
                }
            ]

        return [{"tool": "noop", "args": {"reason": "managing company"}}]

    def _worker(self, world: World, agent: Agent, tick: int) -> list[dict[str, Any]]:
        if agent.employer_company_id:
            # occasional retail buy of listed stock if optimistic
            if tick >= 14 and agent.opinion_economy > 0.05 and world.market.listings:
                sym = next(iter(world.market.listings.keys()))
                L = world.market.listings[sym]
                cash = world.ledger.get(agent.cash_account_id).balance_cents
                price = max(100, int(L.last_price_cents * 1.01))
                qty = min(5, cash // price)
                if qty >= 1 and tick % 5 == agent.id.__hash__() % 5:
                    return [
                        {
                            "tool": "place_order",
                            "args": {
                                "symbol": sym,
                                "side": "buy",
                                "qty": qty,
                                "price_cents": price,
                            },
                        }
                    ]
            return [{"tool": "work", "args": {}}]
        open_jobs = [j for j in world.job_postings.values() if j.open]
        if open_jobs:
            open_jobs.sort(key=lambda j: j.wage_cents_day, reverse=True)
            for j in open_jobs:
                if agent.id not in j.applicants:
                    return [{"tool": "apply_job", "args": {"posting_id": j.id}}]
        return [{"tool": "noop", "args": {"reason": "job hunting"}}]

    def _vc(self, world: World, agent: Agent, tick: int) -> list[dict[str, Any]]:
        pending = [
            d for d in world.vc_deals.values() if d.status == "pitched" and d.vc_agent_id == agent.id
        ]
        if not pending:
            pending = [d for d in world.vc_deals.values() if d.status == "pitched"]
        if pending:
            deal = pending[0]
            co = world.companies.get(deal.company_id)
            # simple underwriting: fund if company has employees or inventory or cash
            approve = True
            if co:
                emps = sum(1 for e in world.employments.values() if e.company_id == co.id and e.active)
                approve = emps >= 0 and deal.amount_cents <= 10_000_000
            return [
                {
                    "tool": "decide_vc",
                    "args": {"deal_id": deal.id, "approve": approve},
                }
            ]
        return [{"tool": "noop", "args": {"reason": "sourcing deals"}}]

    def _trader(self, world: World, agent: Agent, tick: int) -> list[dict[str, Any]]:
        if not world.market.listings:
            return [{"tool": "noop", "args": {"reason": "waiting for listings"}}]
        sym = next(iter(world.market.listings.keys()))
        L = world.market.listings[sym]
        cash = world.ledger.get(agent.cash_account_id).balance_cents
        held = world.market.get_holding(agent.id, sym)
        # news sentiment bias
        sent = 0.0
        if world.news:
            sent = sum(n.sentiment for n in world.news[-5:]) / min(5, len(world.news[-5:]))
        bias = sent + agent.opinion_economy * 0.5
        if bias >= 0 and cash > L.last_price_cents * 10:
            price = int(L.last_price_cents * (1.02 if bias > 0.2 else 1.0))
            qty = min(50, max(1, cash // (price * 4)))
            return [
                {
                    "tool": "place_order",
                    "args": {"symbol": sym, "side": "buy", "qty": qty, "price_cents": price},
                }
            ]
        if held > 0 and bias < -0.1:
            price = max(100, int(L.last_price_cents * 0.98))
            qty = max(1, held // 4)
            return [
                {
                    "tool": "place_order",
                    "args": {"symbol": sym, "side": "sell", "qty": qty, "price_cents": price},
                }
            ]
        if held == 0 and cash > L.last_price_cents * 5:
            # seed liquidity buy
            price = L.last_price_cents
            qty = min(20, cash // price)
            if qty >= 1:
                return [
                    {
                        "tool": "place_order",
                        "args": {"symbol": sym, "side": "buy", "qty": qty, "price_cents": price},
                    }
                ]
        return [{"tool": "noop", "args": {"reason": "holding"}}]

    def _journalist(self, world: World, agent: Agent, tick: int) -> list[dict[str, Any]]:
        if tick == 0:
            return [{"tool": "noop", "args": {"reason": "researching"}}]
        if any(n.tick == tick and n.author_id == agent.id for n in world.news):
            return [{"tool": "noop", "args": {"reason": "already published today"}}]

        companies = list(world.companies.values())
        loans = [l for l in world.loans.values() if l.status.value == "active"]
        unemployed = sum(
            1 for a in world.agents.values() if a.role == "worker" and not a.employer_company_id
        )
        sick = sum(1 for a in world.agents.values() if a.health == HealthStatus.SICK)
        rate = world.config["policy"]["policy_rate_bps"]
        funded = [d for d in world.vc_deals.values() if d.status == "funded"]
        listings = list(world.market.listings.values())

        if funded and tick <= 20:
            d = funded[-1]
            co = world.companies.get(d.company_id)
            cname = co.name if co else d.company_id
            headline = f"VC pours ${d.amount_cents/100:,.0f} into {cname}"
            body = f"Growth capital lands as labor market shows {unemployed} unemployed workers."
            sentiment = 0.45
        elif listings:
            L = listings[0]
            headline = f"{L.symbol} trades near ${L.last_price_cents/100:.2f}"
            body = (
                f"Listed shares outstanding {L.shares_outstanding}. "
                f"Trades today so far reflected in market clearing. Policy rate {rate/100:.2f}%."
            )
            sentiment = 0.2
        elif companies and tick <= 5:
            co = companies[0]
            headline = f"{co.name} launches amid tight credit (rate {rate/100:.2f}%)"
            body = (
                f"Entrepreneur activity is rising. Bank lending outstanding: "
                f"{sum(l.remaining_cents for l in loans)/100:.0f} USD."
            )
            sentiment = 0.3
        elif sick >= 3:
            headline = "Workforce absences climb as illness spreads"
            body = f"{sick} agents are currently sick, disrupting production and payroll."
            sentiment = -0.4
        elif unemployed == 0 and companies:
            headline = "Labor market tightens as local firms staff up"
            body = "Tracked workers are fully employed. Wages and output may firm."
            sentiment = 0.5
        else:
            headline = f"Day {tick}: markets watch policy rate at {rate/100:.2f}%"
            body = (
                f"Agents: {len(world.agents)}. Companies: {len(companies)}. "
                f"VC deals: {len(world.vc_deals)}. Listings: {len(listings)}."
            )
            sentiment = 0.0

        return [
            {
                "tool": "publish_article",
                "args": {"headline": headline, "body": body, "sentiment": sentiment},
            }
        ]

    def _economist(self, world: World, agent: Agent, tick: int) -> list[dict[str, Any]]:
        if tick % 3 != 0:
            return [{"tool": "noop", "args": {"reason": "gathering data"}}]
        m = world.metrics
        note = (
            f"Macro note d{tick}: unemp={m.get('unemployed_workers')} "
            f"loans=${m.get('loans_outstanding_cents',0)/100:.0f} "
            f"idx={m.get('equity_index_cents',0)/100:.2f} "
            f"opinion={m.get('avg_opinion_economy')}"
        )
        agent.remember(tick, note, importance=0.75, kind="semantic")
        return [{"tool": "noop", "args": {"reason": note}}]

    def _politician(self, world: World, agent: Agent, tick: int) -> list[dict[str, Any]]:
        if tick % 5 != 0:
            return [{"tool": "noop", "args": {"reason": "constituency work"}}]
        op = world.metrics.get("avg_opinion_economy", 0)
        if op < -0.1:
            agent.remember(tick, "Public mood souring; consider stimulus narrative", 0.7)
        else:
            agent.remember(tick, "Public mood stable; defend current policy stance", 0.5)
        return [{"tool": "noop", "args": {"reason": "messaging"}}]


class AgentRuntime:
    def __init__(self, llm: Optional[LLMRouter] = None, use_llm: bool = True) -> None:
        self.llm = llm or LLMRouter()
        self.use_llm = use_llm
        self.rules = RulePolicy()
        self.reflection_interval = 5

    def observe(self, world: World, agent: Agent) -> dict[str, Any]:
        cash = world.ledger.get(agent.cash_account_id).balance_cents
        return {
            "tick": world.tick,
            "agent": agent.to_public_dict(),
            "cash_cents": cash,
            "companies": [c.to_dict() for c in world.companies.values()],
            "open_jobs": [j.to_dict() for j in world.job_postings.values() if j.open],
            "loans": [
                l.to_dict()
                for l in world.loans.values()
                if l.borrower_id in (agent.id, agent.founded_company_id or "")
            ],
            "vc_deals": [d.to_dict() for d in list(world.vc_deals.values())[-5:]],
            "market": world.market.book_snapshot(),
            "recent_news": [n.to_dict() for n in world.news[-5:]],
            "memories": [m.to_dict() for m in agent.recent_memories(8)],
            "goals": agent.goals,
            "policy_rate_bps": world.config["policy"]["policy_rate_bps"],
        }

    def maybe_reflect(self, world: World, agent: Agent) -> None:
        if world.tick - agent.last_reflection_tick < self.reflection_interval:
            return
        if len(agent.memories) < 3:
            return
        recent = agent.recent_memories(10)
        # rule-based reflection (LLM optional later)
        themes = []
        text_blob = " ".join(m.content.lower() for m in recent)
        if "loan" in text_blob or "fund" in text_blob or "vc" in text_blob:
            themes.append("capital access is shaping my path")
        if "hired" in text_blob or "job" in text_blob or "work" in text_blob:
            themes.append("labor market outcomes matter to me")
        if "sick" in text_blob or "ill" in text_blob:
            themes.append("health risk can disrupt plans")
        if "news" in text_blob:
            themes.append("media is influencing my outlook")
        if "trade" in text_blob or "list" in text_blob:
            themes.append("markets create new opportunity and risk")
        if not themes:
            themes.append("I am adapting day by day in this economy")
        cash = world.ledger.get(agent.cash_account_id).balance_cents
        summary = (
            f"Reflection d{world.tick}: As a {agent.role}, {'; '.join(themes)}. "
            f"Cash about ${cash/100:.0f}. Goals: {', '.join(agent.goals[:2])}."
        )
        agent.reflect(world.tick, summary, importance=0.85)

    def decide(self, world: World, agent: Agent) -> list[dict[str, Any]]:
        self.maybe_reflect(world, agent)
        if self.use_llm and self.llm.available() and agent.role in (
            "entrepreneur",
            "journalist",
            "vc",
            "trader",
        ):
            actions = self._llm_decide(world, agent)
            if actions:
                return actions
        return self.rules.decide(world, agent)

    def _llm_decide(self, world: World, agent: Agent) -> list[dict[str, Any]]:
        obs = self.observe(world, agent)
        system = (
            "You are an agent in SimEconomy. Respond with ONLY a JSON array of actions. "
            'Each: {"tool": name, "args": {...}}. '
            "Tools: create_company(name), apply_loan(amount_cents, purpose, borrower_type?), "
            "capitalize_company(company_id, amount_cents), post_job(...), apply_job, hire, work, "
            "pitch_vc(company_id, amount_cents, pitch_note), decide_vc(deal_id, approve), "
            "list_company(company_id, symbol, ipo_price_cents), "
            "place_order(symbol, side, qty, price_cents), "
            "publish_article(headline, body, sentiment), noop(reason). Max 2 actions."
        )
        user = f"Role={agent.role} Name={agent.name}\nObservation:\n{obs}\nChoose actions."
        resp = self.llm.complete(system, user, temperature=0.2)
        if not resp.ok:
            return []
        return LLMRouter.parse_json_actions(resp.text)[:2]

    def execute(self, world: World, agent: Agent, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        auth = world.authority
        for act in actions:
            tool = act.get("tool")
            args = act.get("args") or {}
            result: Any
            try:
                if tool == "noop":
                    result = {"ok": True, "reason": args.get("reason", "")}
                elif tool == "create_company":
                    result = auth.create_company(agent.id, str(args.get("name", "NewCo")))
                elif tool == "apply_loan":
                    result = auth.apply_loan(
                        borrower_id=args.get("borrower_id") or agent.id,
                        amount_cents=int(args.get("amount_cents", 0)),
                        purpose=str(args.get("purpose", "")),
                        borrower_type=str(args.get("borrower_type", "agent")),
                    )
                elif tool == "capitalize_company":
                    co_id = args.get("company_id") or agent.founded_company_id
                    amount = int(args.get("amount_cents", 0))
                    if not co_id or co_id not in world.companies:
                        result = {"ok": False, "reason": "no company"}
                    else:
                        co = world.companies[co_id]
                        result = auth.transfer(
                            agent.cash_account_id,
                            co.cash_account_id,
                            amount,
                            f"Capital injection into {co.name}",
                            ref=co_id,
                        )
                elif tool == "post_job":
                    result = auth.post_job(
                        str(args.get("company_id") or agent.founded_company_id),
                        str(args.get("title", "Employee")),
                        int(args.get("wage_cents_day", 15000)),
                    )
                elif tool == "apply_job":
                    result = auth.apply_job(agent.id, str(args.get("posting_id")))
                elif tool == "hire":
                    result = auth.hire(
                        str(args.get("company_id") or agent.founded_company_id),
                        str(args.get("agent_id")),
                        str(args.get("posting_id")),
                    )
                elif tool == "work":
                    result = {"ok": True, "note": "work recorded at payroll phase"}
                elif tool == "publish_article":
                    result = auth.publish_news(
                        agent.id,
                        str(args.get("headline", "Update")),
                        str(args.get("body", "")),
                        float(args.get("sentiment", 0.0)),
                    )
                elif tool == "pitch_vc":
                    result = auth.pitch_to_vc(
                        agent.id,
                        str(args.get("company_id") or agent.founded_company_id),
                        int(args.get("amount_cents", 0)),
                        str(args.get("pitch_note", "")),
                        args.get("vc_agent_id"),
                    )
                elif tool == "decide_vc":
                    result = auth.decide_vc_deal(
                        agent.id,
                        str(args.get("deal_id")),
                        bool(args.get("approve", True)),
                    )
                elif tool == "list_company":
                    result = auth.list_company(
                        agent.id,
                        str(args.get("company_id") or agent.founded_company_id),
                        str(args.get("symbol", "CO")),
                        int(args.get("ipo_price_cents", 1000)),
                    )
                elif tool == "place_order":
                    result = auth.place_order(
                        agent.id,
                        str(args.get("symbol")),
                        str(args.get("side", "buy")),
                        int(args.get("qty", 0)),
                        int(args.get("price_cents", 0)),
                    )
                else:
                    result = {"ok": False, "reason": f"unknown tool {tool}"}
            except Exception as e:
                result = {"ok": False, "reason": str(e)}

            if hasattr(result, "to_dict"):
                result = result.to_dict()
                result["ok"] = False
            results.append({"tool": tool, "args": args, "result": result})
            agent.remember(world.tick, f"Action {tool} -> {result}", importance=0.55)
        return results
