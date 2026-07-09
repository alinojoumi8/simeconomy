"""Core domain models for SimEconomy Phase 0."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional
import uuid


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}" if prefix else uuid.uuid4().hex[:12]


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    SICK = "sick"


class LoanStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    PAID = "paid"
    DEFAULTED = "defaulted"


class CompanyStatus(str, Enum):
    ACTIVE = "active"
    DISSOLVED = "dissolved"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass
class Persona:
    political_lean: str = "center"
    risk_tolerance: float = 0.5
    skills: dict[str, int] = field(default_factory=dict)
    occupation: str = "worker"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryItem:
    tick: int
    content: str
    importance: float = 0.5
    kind: str = "episodic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Agent:
    id: str
    name: str
    role: str
    persona: Persona
    health: HealthStatus = HealthStatus.HEALTHY
    sick_days_remaining: int = 0
    employer_company_id: Optional[str] = None
    founded_company_id: Optional[str] = None
    cash_account_id: str = ""
    memories: list[MemoryItem] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)

    def is_working_today(self) -> bool:
        return self.health == HealthStatus.HEALTHY and self.employer_company_id is not None

    def remember(self, tick: int, content: str, importance: float = 0.5, kind: str = "episodic") -> None:
        self.memories.append(MemoryItem(tick=tick, content=content, importance=importance, kind=kind))
        if len(self.memories) > 200:
            self.memories = self.memories[-200:]

    def recent_memories(self, k: int = 8) -> list[MemoryItem]:
        scored = sorted(
            self.memories,
            key=lambda m: (m.tick * 0.01 + m.importance),
            reverse=True,
        )
        return scored[:k]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "occupation": self.persona.occupation,
            "health": self.health.value,
            "sick_days_remaining": self.sick_days_remaining,
            "employer_company_id": self.employer_company_id,
            "founded_company_id": self.founded_company_id,
            "cash_account_id": self.cash_account_id,
            "political_lean": self.persona.political_lean,
            "risk_tolerance": self.persona.risk_tolerance,
            "skills": self.persona.skills,
            "goals": self.goals,
            "memory_count": len(self.memories),
        }


@dataclass
class Account:
    id: str
    owner_type: str  # agent | company | institution
    owner_id: str
    name: str
    balance_cents: int = 0
    currency: str = "USD"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_type": self.owner_type,
            "owner_id": self.owner_id,
            "name": self.name,
            "balance_cents": self.balance_cents,
            "balance_usd": round(self.balance_cents / 100.0, 2),
            "currency": self.currency,
        }


@dataclass
class Transaction:
    id: str
    tick: int
    debit_account_id: str
    credit_account_id: str
    amount_cents: int
    memo: str
    ref: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Company:
    id: str
    name: str
    founder_id: str
    cash_account_id: str
    status: CompanyStatus = CompanyStatus.ACTIVE
    inventory_units: int = 0
    product_price_cents: int = 5000
    daily_productivity_per_worker: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "founder_id": self.founder_id,
            "cash_account_id": self.cash_account_id,
            "status": self.status.value,
            "inventory_units": self.inventory_units,
            "product_price_cents": self.product_price_cents,
        }


@dataclass
class Loan:
    id: str
    bank_id: str
    borrower_type: str  # agent | company
    borrower_id: str
    principal_cents: int
    remaining_cents: int
    rate_bps: int
    status: LoanStatus
    purpose: str = ""
    tick_origin: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["principal_usd"] = round(self.principal_cents / 100.0, 2)
        return d


@dataclass
class JobPosting:
    id: str
    company_id: str
    title: str
    wage_cents_day: int
    open: bool = True
    applicants: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "title": self.title,
            "wage_cents_day": self.wage_cents_day,
            "wage_usd_day": round(self.wage_cents_day / 100.0, 2),
            "open": self.open,
            "applicants": list(self.applicants),
        }


@dataclass
class Employment:
    agent_id: str
    company_id: str
    wage_cents_day: int
    active: bool = True
    posting_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NewsItem:
    id: str
    tick: int
    author_id: str
    headline: str
    body: str
    sentiment: float = 0.0  # -1..1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Event:
    tick: int
    kind: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ShockEvent:
    tick: int
    type: str
    params: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Reject:
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"ok": False, "reason": self.reason}
