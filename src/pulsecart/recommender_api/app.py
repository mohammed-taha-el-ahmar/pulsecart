"""Recommender API + dashboard.

Reads the latest scored EnrichedEvent per user from the warehouse and returns
its top-K recommendations. The dashboard (index.html) polls /summary and
/recent for a real-time-ish live view.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pulsecart.config import Settings, get_settings
from pulsecart.warehouse.warehouse import DuckDBWarehouse

_HERE = Path(__file__).parent
_STATIC = _HERE / "static"


def create_app(
    settings: Settings | None = None,
    warehouse: DuckDBWarehouse | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    warehouse = warehouse or DuckDBWarehouse(settings.duckdb_path)

    app = FastAPI(title="PulseCart Recommender", version="0.1.0")
    app.state.warehouse = warehouse

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/summary")
    def summary() -> dict[str, Any]:
        return app.state.warehouse.summary()

    @app.get("/recent/{user_id}")
    def recent(user_id: str, limit: int = 10) -> dict[str, Any]:
        rows = app.state.warehouse.latest_for_user(user_id, limit=limit)
        return {"user_id": user_id, "events": rows}

    @app.get("/recommendations/{user_id}")
    def recommendations(user_id: str) -> dict[str, Any]:
        rows = app.state.warehouse.latest_for_user(user_id, limit=1)
        if not rows:
            raise HTTPException(status_code=404, detail=f"no scored events for user {user_id}")
        latest = rows[0]
        return {
            "user_id": user_id,
            "trace_id": latest["trace_id"],
            "model_version": latest["model_version"],
            "recommendations": latest["recommendations"],
            "scored_at": str(latest["event_ts"]),
        }

    if _STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(str(_STATIC / "index.html"))

    return app


app = create_app()
