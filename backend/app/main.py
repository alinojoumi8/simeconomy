"""FastAPI control plane + static dashboard for SimEconomy."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.agents.orchestrator import SimulationOrchestrator

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "baseline_csus.yaml"
FRONTEND = ROOT / "frontend"

app = FastAPI(
    title="SimEconomy",
    version="0.2.0",
    description="Multi-agent economic simulator — Phase 1",
)
orch = SimulationOrchestrator(CONFIG, use_llm=False)

# live websocket clients
_ws_clients: set[WebSocket] = set()


def _broadcast_event(ev) -> None:
    data = json.dumps(ev.to_dict())

    async def _send_all() -> None:
        dead = []
        for ws in list(_ws_clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_clients.discard(ws)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_send_all())
    except RuntimeError:
        pass


orch.world.on_event(_broadcast_event)


class StepBody(BaseModel):
    n: int = Field(1, ge=1, le=365)


class ShockBody(BaseModel):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class ResetBody(BaseModel):
    seed: Optional[int] = None


class AutoBody(BaseModel):
    interval_sec: float = Field(1.0, ge=0.2, le=60.0)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.2.0", "phase": "1"}


@app.get("/state")
def get_state() -> dict[str, Any]:
    return orch.state()


@app.get("/agents")
def list_agents() -> list[dict[str, Any]]:
    st = orch.state()
    return st["agents"]


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str) -> dict[str, Any]:
    w = orch.world
    if agent_id not in w.agents:
        return {"error": "not found"}
    a = w.agents[agent_id]
    return {
        **a.to_public_dict(),
        "cash_cents": w.ledger.get(a.cash_account_id).balance_cents,
        "memories": [m.to_dict() for m in a.memories[-30:]],
        "reflections": [m.to_dict() for m in a.reflections[-10:]],
    }


@app.get("/accounts")
def accounts() -> list[dict[str, Any]]:
    return orch.world.ledger.balances_public()


@app.get("/events")
def events(limit: int = 100) -> list[dict[str, Any]]:
    return [e.to_dict() for e in orch.world.events[-limit:]]


@app.get("/news")
def news(limit: int = 50) -> list[dict[str, Any]]:
    return [n.to_dict() for n in orch.world.news[-limit:]]


@app.get("/market")
def market() -> dict[str, Any]:
    return orch.world.market.book_snapshot()


@app.get("/vc")
def vc_deals() -> list[dict[str, Any]]:
    return [d.to_dict() for d in orch.world.vc_deals.values()]


@app.get("/metrics/history")
def metrics_history(limit: int = 90) -> list[dict[str, Any]]:
    return orch.world.metrics_history[-limit:]


@app.post("/pause")
def pause() -> dict[str, Any]:
    return orch.pause()


@app.post("/resume")
def resume() -> dict[str, Any]:
    return orch.resume()


@app.post("/step")
def step(body: StepBody | None = None) -> dict[str, Any]:
    n = body.n if body else 1
    return orch.step(n)


@app.post("/shock")
def shock(body: ShockBody) -> dict[str, Any]:
    return orch.inject_shock(body.type, body.params)


@app.post("/reset")
def reset(body: ResetBody | None = None) -> dict[str, Any]:
    seed = body.seed if body else None
    return orch.reset(seed=seed)


@app.post("/auto/start")
def auto_start(body: AutoBody | None = None) -> dict[str, Any]:
    interval = body.interval_sec if body else 1.0
    return orch.start_auto(interval)


@app.post("/auto/stop")
def auto_stop() -> dict[str, str]:
    orch.stop_auto()
    orch.world.paused = True
    return {"auto": "stopped"}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _ws_clients.add(ws)
    try:
        await ws.send_text(json.dumps({"kind": "hello", "state": orch.state()["metrics"]}))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
