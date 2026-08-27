"""
charon/gateway/routes/__init__.py
System Version: v3.3.0

Module: Gateway API Routes Package Init.
Aggregates sub-routers into a unified master API router for daemon mounting.
"""

from fastapi import APIRouter

from charon.gateway.routes.routing import router as router_control_api
from charon.gateway.routes.health import router as health_router
from charon.gateway.routes.skills import router as skills_router
from charon.gateway.routes.websocket import router as websocket_router
from charon.gateway.routes.concierge import router as concierge_router
from charon.gateway.routes.docs import router as docs_router
from charon.gateway.routes.journal import router as journal_router
from charon.gateway.routes.system import router as system_router
from charon.gateway.routes.avatar import router as avatar_router

router = APIRouter()

# Mount feature sub-routers
router.include_router(router_control_api)
router.include_router(health_router)
router.include_router(skills_router)
router.include_router(websocket_router)
router.include_router(concierge_router)
router.include_router(docs_router)
router.include_router(journal_router)
router.include_router(system_router)
router.include_router(avatar_router)