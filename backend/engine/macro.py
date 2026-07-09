"""Macroeconomic aggregates for research metrics (Phase 2+)."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .world import World

from .models import HealthStatus, LoanStatus


def compute_macro(world: "World") -> dict[str, Any]:
    """Compute daily macro snapshot; pure function over world state."""
    w = world
    workers = [a for a in w.agents.values() if a.role == "worker"]
    employed = [a for a in workers if a.employer_company_id]
    unemployed = [a for a in workers if not a.employer_company_id]
    lf = max(1, len(workers))
    u_rate = len(unemployed) / lf

    # GDP proxy: sales + wages paid approximation from today metrics + inventory value
    sales = int(w.metrics.get("sales_cents_today", 0))
    prod_units = int(w.metrics.get("production_units_today", 0))
    avg_price = 5000
    if w.companies:
        avg_price = int(
            sum(c.product_price_cents for c in w.companies.values()) / max(1, len(w.companies))
        )
    gdp_proxy = sales + prod_units * avg_price // 2

    # CPI: base 100 scaled by energy and average product prices
    energy = float(w.config.get("markets", {}).get("energy_price_index", 100.0))
    cpi = 100.0 * (0.7 * (avg_price / 5000.0) + 0.3 * (energy / 100.0))

    # inflation vs previous CPI if available
    prev_cpi = None
    if w.metrics_history:
        prev_cpi = w.metrics_history[-1].get("cpi")
    inflation = 0.0
    if prev_cpi and prev_cpi > 0:
        inflation = (cpi / prev_cpi) - 1.0

    wages = []
    for e in w.employments.values():
        if e.active:
            wages.append(e.wage_cents_day)
    avg_wage = int(sum(wages) / len(wages)) if wages else 0

    loans_out = sum(l.remaining_cents for l in w.loans.values() if l.status == LoanStatus.ACTIVE)
    bank = w.institutions.get("bank")
    bank_cash = w.ledger.get(bank["cash_account_id"]).balance_cents if bank else 0
    credit_ratio = loans_out / max(1, bank_cash + loans_out)

    # simple Gini on agent cash
    cashes = sorted(
        w.ledger.get(a.cash_account_id).balance_cents for a in w.agents.values()
    )
    gini = _gini(cashes)

    sick = sum(1 for a in w.agents.values() if a.health == HealthStatus.SICK)
    dead = sum(1 for a in w.agents.values() if getattr(a, "alive", True) is False)

    listings = list(w.market.listings.values())
    equity_index = (
        int(sum(L.last_price_cents for L in listings) / len(listings)) if listings else 0
    )

    avg_opinion = (
        sum(a.opinion_economy for a in w.agents.values() if getattr(a, "alive", True))
        / max(1, sum(1 for a in w.agents.values() if getattr(a, "alive", True)))
    )

    return {
        "gdp_proxy_cents": gdp_proxy,
        "cpi": round(cpi, 3),
        "inflation_daily": round(inflation, 6),
        "unemployment_rate": round(u_rate, 4),
        "labor_force": len(workers),
        "employed_workers": len(employed),
        "unemployed_workers": len(unemployed),
        "avg_wage_cents_day": avg_wage,
        "energy_price_index": energy,
        "credit_ratio": round(credit_ratio, 4),
        "gini_cash": round(gini, 4),
        "sick_agents": sick,
        "deceased_agents": dead,
        "equity_index_cents": equity_index,
        "avg_opinion_economy": round(avg_opinion, 3),
        "population_alive": sum(1 for a in w.agents.values() if getattr(a, "alive", True)),
    }


def _gini(values: list[int]) -> float:
    if not values:
        return 0.0
    n = len(values)
    total = sum(values)
    if total <= 0:
        return 0.0
    cum = 0
    gini_sum = 0
    for i, v in enumerate(sorted(values), start=1):
        cum += v
        gini_sum += i * v
    # Gini = (2*sum(i*x_i))/(n*sum(x)) - (n+1)/n
    return max(0.0, min(1.0, (2 * gini_sum) / (n * total) - (n + 1) / n))
