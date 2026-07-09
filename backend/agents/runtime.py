"""Agent decision loop: LLM tools or rule policy → World Authority."""

from __future__ import annotations

from typing import Any, Optional

from backend.engine.models import Agent, HealthStatus
from backend.engine.world import World
from backend.llm.router import LLMRouter


class RulePolicy:
    """Deterministic persona scripts so Phase 0 runs without APIs."""

    def decide(self, world: World, agent: Agent) -> list[dict[str, Any]]:
        if agent.health == HealthStatus.SICK:
            return [{"tool": "noop", "args": {"reason": "sick"}}]

        role = agent.role
        tick = world.tick

        if role == "entrepreneur":
            return self._entrepreneur(world, agent, tick)
        if role == "worker":
            return self._worker(world, agent)
        if role == "journalist":
            return self._journalist(world, agent, tick)
        if role == "lawyer":
            return [{"tool": "noop", "args": {"reason": "awaiting clients"}}]
        if role == "banker":
            return [{"tool": "noop", "args": {"reason": "monitoring portfolio"}}]
        return [{"tool": "noop", "args": {"reason": "no policy"}}]

    def _entrepreneur(self, world: World, agent: Agent, tick: int) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if not agent.founded_company_id:
            if tick >= 1:
                actions.append({"tool": "create_company", "args": {"name": "Northstar Labs"}})
            return actions or [{"tool": "noop", "args": {"reason": "planning venture"}}]

        co_id = agent.founded_company_id
        co = world.companies[co_id]
        co_cash = world.ledger.get(co.cash_account_id).balance_cents

        # Fund company: personal transfer via loan then capitalize
        has_loan = any(
            l.borrower_id in (agent.id, co_id) and l.status.value == "active"
            for l in world.loans.values()
        )
        if not has_loan and tick >= 2:
            actions.append(
                {
                    "tool": "apply_loan",
                    "args": {
                        "amount_cents": 2_000_000,
                        "purpose": "working capital for Northstar Labs",
                        "borrower_type": "agent",
                    },
                }
            )
            return actions

        # Capitalize company from personal cash once
        personal = world.ledger.get(agent.cash_account_id).balance_cents
        if co_cash < 500_000 and personal > 1_000_000 and tick >= 3:
            actions.append(
                {
                    "tool": "capitalize_company",
                    "args": {"company_id": co_id, "amount_cents": min(1_500_000, personal // 2)},
                }
            )
            return actions

        open_for_co = [j for j in world.job_postings.values() if j.company_id == co_id and j.open]
        employed_here = [
            e for e in world.employments.values() if e.company_id == co_id and e.active
        ]
        if not open_for_co and len(employed_here) < 2 and co_cash >= 200_000 and tick >= 4:
            title = "Software Engineer" if len(employed_here) == 0 else "Operations Associate"
            wage = 18000 if "Software" in title else 14000
            actions.append(
                {"tool": "post_job", "args": {"company_id": co_id, "title": title, "wage_cents_day": wage}}
            )
            return actions

        # Hire first applicant on open postings
        for j in world.job_postings.values():
            if j.company_id == co_id and j.open and j.applicants:
                actions.append(
                    {
                        "tool": "hire",
                        "args": {
                            "company_id": co_id,
                            "agent_id": j.applicants[0],
                            "posting_id": j.id,
                        },
                    }
                )
                return actions

        return [{"tool": "noop", "args": {"reason": "managing company"}}]

    def _worker(self, world: World, agent: Agent) -> list[dict[str, Any]]:
        if agent.employer_company_id:
            return [{"tool": "work", "args": {}}]
        open_jobs = [j for j in world.job_postings.values() if j.open]
        if open_jobs:
            # pick highest wage not yet applied
            open_jobs.sort(key=lambda j: j.wage_cents_day, reverse=True)
            for j in open_jobs:
                if agent.id not in j.applicants:
                    return [{"tool": "apply_job", "args": {"posting_id": j.id}}]
        return [{"tool": "noop", "args": {"reason": "job hunting"}}]

    def _journalist(self, world: World, agent: Agent, tick: int) -> list[dict[str, Any]]:
        if tick == 0:
            return [{"tool": "noop", "args": {"reason": "researching"}}]
        # one article per day max (check if already published today)
        if any(n.tick == tick and n.author_id == agent.id for n in world.news):
            return [{"tool": "noop", "args": {"reason": "already published today"}}]

        companies = list(world.companies.values())
        loans = [l for l in world.loans.values() if l.status.value == "active"]
        unemployed = sum(
            1 for a in world.agents.values() if a.role == "worker" and not a.employer_company_id
        )
        sick = sum(1 for a in world.agents.values() if a.health == HealthStatus.SICK)
        rate = world.config["policy"]["policy_rate_bps"]

        if companies and tick <= 5:
            co = companies[0]
            headline = f"{co.name} launches amid tight credit (rate {rate/100:.2f}%)"
            body = (
                f"Entrepreneur activity is rising. {co.name} was incorporated recently. "
                f"Bank lending outstanding: {sum(l.remaining_cents for l in loans)/100:.0f} USD. "
                f"Open labor market: {unemployed} unemployed workers tracked."
            )
            sentiment = 0.3
        elif sick >= 2:
            headline = "Workforce absences climb as illness spreads"
            body = f"{sick} agents are currently sick, disrupting production and payroll."
            sentiment = -0.4
        elif unemployed == 0 and companies:
            headline = "Labor market tightens as local firms staff up"
            body = "All tracked workers are employed. Wages and output may firm."
            sentiment = 0.5
        else:
            headline = f"Day {tick}: markets watch policy rate at {rate/100:.2f}%"
            body = (
                f"Companies: {len(companies)}. Active loans: {len(loans)}. "
                f"Unemployed workers: {unemployed}. Inventory units: "
                f"{sum(c.inventory_units for c in companies)}."
            )
            sentiment = 0.0

        return [
            {
                "tool": "publish_article",
                "args": {"headline": headline, "body": body, "sentiment": sentiment},
            }
        ]


class AgentRuntime:
    def __init__(self, llm: Optional[LLMRouter] = None, use_llm: bool = True) -> None:
        self.llm = llm or LLMRouter()
        self.use_llm = use_llm
        self.rules = RulePolicy()

    def observe(self, world: World, agent: Agent) -> dict[str, Any]:
        cash = world.ledger.get(agent.cash_account_id).balance_cents
        return {
            "tick": world.tick,
            "agent": agent.to_public_dict(),
            "cash_cents": cash,
            "companies": [c.to_dict() for c in world.companies.values()],
            "open_jobs": [j.to_dict() for j in world.job_postings.values() if j.open],
            "loans": [l.to_dict() for l in world.loans.values() if l.borrower_id in (agent.id, agent.founded_company_id or "")],
            "recent_news": [n.to_dict() for n in world.news[-5:]],
            "memories": [m.to_dict() for m in agent.recent_memories(6)],
            "goals": agent.goals,
            "policy_rate_bps": world.config["policy"]["policy_rate_bps"],
        }

    def decide(self, world: World, agent: Agent) -> list[dict[str, Any]]:
        # Prefer rules for reliability in Phase 0 unless explicitly forced and available
        if self.use_llm and self.llm.available() and agent.role in ("entrepreneur", "journalist"):
            actions = self._llm_decide(world, agent)
            if actions:
                return actions
        return self.rules.decide(world, agent)

    def _llm_decide(self, world: World, agent: Agent) -> list[dict[str, Any]]:
        obs = self.observe(world, agent)
        system = (
            "You are an agent in SimEconomy, a realistic economic simulation. "
            "Respond with ONLY a JSON array of actions. Each action: "
            '{"tool": "<name>", "args": {...}}. '
            "Tools: create_company(name), apply_loan(amount_cents, purpose, borrower_type?), "
            "capitalize_company(company_id, amount_cents), post_job(company_id, title, wage_cents_day), "
            "apply_job(posting_id), hire(company_id, agent_id, posting_id), work(), "
            "publish_article(headline, body, sentiment), noop(reason). "
            "Never invent account balances; use observation. Max 2 actions."
        )
        user = f"Role={agent.role} Name={agent.name}\nObservation:\n{obs}\nChoose actions for today."
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
                else:
                    result = {"ok": False, "reason": f"unknown tool {tool}"}
            except Exception as e:
                result = {"ok": False, "reason": str(e)}

            if hasattr(result, "to_dict"):
                result = result.to_dict()
                result["ok"] = False
            results.append({"tool": tool, "args": args, "result": result})
            agent.remember(
                world.tick,
                f"Action {tool} -> {result}",
                importance=0.55,
            )
        return results
