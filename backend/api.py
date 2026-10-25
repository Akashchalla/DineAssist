"""Local JSON API. Run one server process; run the detector separately."""

import asyncio
from contextlib import asynccontextmanager, suppress
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.state import Conflict, TableStore
from backend.waitlist import NotifyError, Waitlist, send_ntfy

ROOT = Path(__file__).resolve().parents[1]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class StartRun(StrictBody):
    mode: Literal["video", "live"] = "video"
    greeting_seconds: float = Field(default=300, gt=0, le=86400)


class Person(StrictBody):
    track_id: int | None = Field(default=None, ge=0)
    table_id: str | None = None


class Observation(StrictBody):
    frame_number: int = Field(ge=0)
    media_seconds: float | None = Field(default=None, ge=0)
    people: list[Person] = Field(max_length=1000)


class StopRun(StrictBody):
    reason: Literal["completed", "stopped", "disconnected"] = "stopped"


class RunReference(StrictBody):
    run_id: str


class NewParty(StrictBody):
    name: str = Field(min_length=1, max_length=40)
    party_size: int = Field(ge=1, le=20)
    # Optional personal ntfy topic; otherwise the restaurant's topic is used.
    topic: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")


class NotifyParty(StrictBody):
    table_id: str


class CloseParty(StrictBody):
    status: Literal["seated", "removed"]


def create_app(database=None, zones=None, clock=None, sender=None):
    @asynccontextmanager
    async def lifespan(app):
        kwargs = {} if clock is None else {"clock": clock}
        app.state.store = TableStore(
            database or os.environ.get("RESTAURANT_DB", str(ROOT / "data/restaurant.sqlite3")),
            zones or os.environ.get("RESTAURANT_ZONES", str(ROOT / "data/zones/tables.json")), **kwargs,
        )
        app.state.waitlist = Waitlist(app.state.store,
                                      server=os.environ.get("RESTAURANT_NTFY_SERVER", "https://ntfy.sh"),
                                      topic=os.environ.get("RESTAURANT_NTFY_TOPIC") or None,
                                      sender=sender or send_ntfy)

        async def check_timers():
            while True:
                await asyncio.sleep(0.5)
                await asyncio.to_thread(app.state.store.tick)

        task = asyncio.create_task(check_timers())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            app.state.store.close()

    app = FastAPI(title="Restaurant Table Monitor", version="0.3.0", lifespan=lifespan,
                  description="Local learning prototype. Run on 127.0.0.1 with one worker. Staff labels are manual and scoped to a run.")

    @app.exception_handler(Conflict)
    async def conflict_handler(request, error):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(KeyError)
    async def missing_handler(request, error):
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(ValueError)
    async def invalid_handler(request, error):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(NotifyError)
    async def notify_handler(request, error):
        return JSONResponse(status_code=502, content={"detail": str(error)})

    @app.get("/health")
    def health():
        return {"status": "ok", "phase": 3}

    @app.get("/api/tables")
    def tables(request: Request):
        return request.app.state.store.snapshot()

    @app.post("/api/runs", status_code=201)
    def start(body: StartRun, request: Request):
        return request.app.state.store.start(body.mode, body.greeting_seconds)

    @app.post("/api/runs/{run_id}/observations")
    def observations(run_id: str, body: Observation, request: Request):
        return request.app.state.store.observe(run_id, body.frame_number, body.media_seconds,
                                               [person.model_dump() for person in body.people])

    @app.post("/api/runs/{run_id}/stop")
    def stop(run_id: str, body: StopRun, request: Request):
        return request.app.state.store.stop(run_id, body.reason)

    @app.post("/api/tables/{table_id}/greet")
    def greet(table_id: str, body: RunReference, request: Request):
        return request.app.state.store.staff_action(body.run_id, table_id, "greet")

    @app.post("/api/tables/{table_id}/clean")
    def clean(table_id: str, body: RunReference, request: Request):
        return request.app.state.store.staff_action(body.run_id, table_id, "clean")

    @app.post("/api/staff/{track_id}")
    def staff(track_id: int, body: RunReference, request: Request):
        return request.app.state.store.mark_staff(body.run_id, track_id)

    @app.delete("/api/staff/{track_id}")
    def remove_staff(track_id: int, body: RunReference, request: Request):
        return request.app.state.store.mark_staff(body.run_id, track_id, False)

    @app.get("/api/events")
    def events(request: Request, after_id: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), run_id: str | None = None):
        return request.app.state.store.events(after_id, limit, run_id)

    @app.get("/api/alerts")
    def alerts(request: Request, after_id: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), run_id: str | None = None):
        return request.app.state.store.events(after_id, limit, run_id, True)

    @app.get("/api/waitlist")
    def waitlist(request: Request):
        return request.app.state.waitlist.listing()

    @app.post("/api/waitlist", status_code=201)
    def add_party(body: NewParty, request: Request):
        return request.app.state.waitlist.add(body.name, body.party_size, body.topic)

    @app.post("/api/waitlist/{entry_id}/notify")
    def notify_party(entry_id: int, body: NotifyParty, request: Request):
        return request.app.state.waitlist.notify(entry_id, body.table_id)

    @app.post("/api/waitlist/{entry_id}/close")
    def close_party(entry_id: int, body: CloseParty, request: Request):
        return request.app.state.waitlist.close(entry_id, body.status)

    return app


app = create_app()
