import logging

from fastapi import APIRouter, Response
from sqlalchemy import text
from temporalio.client import Client

from app.config import settings
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter()


def _check_db() -> bool:
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("db health check failed: %s", exc)
        return False


async def _check_temporal() -> bool:
    try:
        await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
        return True
    except Exception as exc:
        logger.warning("temporal health check failed: %s", exc)
        return False


@router.get(
    "/health",
    summary="Liveness + dependency check",
    response_description="Service state plus each dependency's status",
)
async def health(response: Response) -> dict:
    """
    Returns 200 only if both Postgres and Temporal are reachable from the
    API container
    """
    db_ok = _check_db()
    temporal_ok = await _check_temporal()
    ok = db_ok and temporal_ok
    if not ok:
        response.status_code = 503
    return {
        "ok": ok,
        "db": "ok" if db_ok else "down",
        "temporal": "ok" if temporal_ok else "down",
    }
