"""Deterministic equity order book (Phase 1)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .models import OrderSide, OrderStatus, new_id


@dataclass
class EquityOrder:
    id: str
    tick: int
    agent_id: str
    symbol: str
    side: OrderSide
    qty: int
    price_cents: int
    status: OrderStatus = OrderStatus.OPEN
    filled_qty: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tick": self.tick,
            "agent_id": self.agent_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "qty": self.qty,
            "price_cents": self.price_cents,
            "price_usd": round(self.price_cents / 100.0, 2),
            "status": self.status.value,
            "filled_qty": self.filled_qty,
        }


@dataclass
class Trade:
    id: str
    tick: int
    symbol: str
    price_cents: int
    qty: int
    buy_order_id: str
    sell_order_id: str
    buyer_id: str
    seller_id: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["price_usd"] = round(self.price_cents / 100.0, 2)
        d["notional_cents"] = self.price_cents * self.qty
        return d


@dataclass
class Listing:
    symbol: str
    company_id: str
    shares_outstanding: int
    last_price_cents: int
    listed_tick: int
    float_shares: int  # tradable float (ex founder lockup optional)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "company_id": self.company_id,
            "shares_outstanding": self.shares_outstanding,
            "float_shares": self.float_shares,
            "last_price_cents": self.last_price_cents,
            "last_price_usd": round(self.last_price_cents / 100.0, 2),
            "listed_tick": self.listed_tick,
            "market_cap_cents": self.last_price_cents * self.shares_outstanding,
        }


@dataclass
class ShareHolding:
    agent_id: str
    symbol: str
    shares: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OrderBook:
    """Price-time priority matching for a single symbol book set."""

    def __init__(self) -> None:
        self.orders: dict[str, EquityOrder] = {}
        self.trades: list[Trade] = []
        self.listings: dict[str, Listing] = {}
        # (agent_id, symbol) -> shares
        self.holdings: dict[tuple[str, str], int] = {}

    def get_holding(self, agent_id: str, symbol: str) -> int:
        return self.holdings.get((agent_id, symbol), 0)

    def set_holding(self, agent_id: str, symbol: str, shares: int) -> None:
        if shares <= 0:
            self.holdings.pop((agent_id, symbol), None)
        else:
            self.holdings[(agent_id, symbol)] = shares

    def add_shares(self, agent_id: str, symbol: str, delta: int) -> None:
        cur = self.get_holding(agent_id, symbol)
        self.set_holding(agent_id, symbol, cur + delta)

    def place(
        self,
        tick: int,
        agent_id: str,
        symbol: str,
        side: OrderSide,
        qty: int,
        price_cents: int,
    ) -> EquityOrder:
        order = EquityOrder(
            id=new_id("ord_"),
            tick=tick,
            agent_id=agent_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price_cents=price_cents,
        )
        self.orders[order.id] = order
        return order

    def open_orders(self, symbol: Optional[str] = None) -> list[EquityOrder]:
        out = [o for o in self.orders.values() if o.status == OrderStatus.OPEN]
        if symbol:
            out = [o for o in out if o.symbol == symbol]
        return out

    def match_symbol(self, symbol: str, tick: int) -> list[Trade]:
        """Match open buy/sell for symbol. Returns new trades (cash settlement done by caller)."""
        buys = sorted(
            [o for o in self.open_orders(symbol) if o.side == OrderSide.BUY],
            key=lambda o: (-o.price_cents, o.tick, o.id),
        )
        sells = sorted(
            [o for o in self.open_orders(symbol) if o.side == OrderSide.SELL],
            key=lambda o: (o.price_cents, o.tick, o.id),
        )
        new_trades: list[Trade] = []
        bi = si = 0
        while bi < len(buys) and si < len(sells):
            b, s = buys[bi], sells[si]
            if b.agent_id == s.agent_id:
                # skip self-trade: advance the older side
                if b.tick <= s.tick:
                    bi += 1
                else:
                    si += 1
                continue
            if b.price_cents < s.price_cents:
                break
            # trade at sell price (maker-friendly / common call auction simplification)
            price = s.price_cents
            b_rem = b.qty - b.filled_qty
            s_rem = s.qty - s.filled_qty
            qty = min(b_rem, s_rem)
            if qty <= 0:
                if b_rem <= 0:
                    bi += 1
                if s_rem <= 0:
                    si += 1
                continue
            trade = Trade(
                id=new_id("trd_"),
                tick=tick,
                symbol=symbol,
                price_cents=price,
                qty=qty,
                buy_order_id=b.id,
                sell_order_id=s.id,
                buyer_id=b.agent_id,
                seller_id=s.agent_id,
            )
            new_trades.append(trade)
            self.trades.append(trade)
            b.filled_qty += qty
            s.filled_qty += qty
            if b.filled_qty >= b.qty:
                b.status = OrderStatus.FILLED
                bi += 1
            if s.filled_qty >= s.qty:
                s.status = OrderStatus.FILLED
                si += 1
            if symbol in self.listings:
                self.listings[symbol].last_price_cents = price
        return new_trades

    def match_all(self, tick: int) -> list[Trade]:
        trades: list[Trade] = []
        for symbol in list(self.listings.keys()):
            trades.extend(self.match_symbol(symbol, tick))
        return trades

    def holdings_public(self) -> list[dict[str, Any]]:
        return [
            {"agent_id": a, "symbol": s, "shares": q}
            for (a, s), q in sorted(self.holdings.items())
            if q > 0
        ]

    def book_snapshot(self) -> dict[str, Any]:
        return {
            "listings": [L.to_dict() for L in self.listings.values()],
            "open_orders": [o.to_dict() for o in self.open_orders()],
            "recent_trades": [t.to_dict() for t in self.trades[-40:]],
            "holdings": self.holdings_public(),
        }
