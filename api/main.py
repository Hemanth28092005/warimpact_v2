"""Main FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.aggression import router as aggression_router
from api.routes.alerts import router as alerts_router
from api.routes.brief import router as brief_router
from api.routes.cascade import cascade_router
from api.routes.cii import router as cii_router
from api.routes.dashboard import router as dashboard_router
from api.routes.events import router as events_router
from api.routes.health import router as health_router
from api.routes.live_feed import router as live_feed_router
from api.routes.markets import router as markets_router
from api.routes.sage import router as sage_router
from api.routes.sage_tts import router as sage_tts_router

app = FastAPI(
    title="S.A.G.E Platform API",
    description="S.A.G.E — Strategic Advisory & Geopolitical Evaluation Platform REST API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(cii_router)
app.include_router(aggression_router)
app.include_router(live_feed_router)
app.include_router(cascade_router)
app.include_router(dashboard_router)
app.include_router(markets_router)
app.include_router(events_router)
app.include_router(brief_router)
app.include_router(alerts_router)
app.include_router(sage_router)
app.include_router(sage_tts_router)
app.include_router(health_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "S.A.G.E Platform API v1.0.0 operational"}
