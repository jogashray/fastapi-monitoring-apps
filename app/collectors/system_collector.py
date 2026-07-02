"""Background async task that periodically refreshes system metrics."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.config import settings
from app.metrics.system_metrics import update_system_metrics

logger = logging.getLogger(__name__)


async def _collect_loop() -> None:
    """Run `update_system_metrics` in an infinite loop until cancelled."""
    interval = settings.system_metrics_interval
    logger.info("System metrics collector started (interval=%ss)", interval)
    try:
        while True:
            try:
                update_system_metrics()
            except Exception as exc:  # noqa: BLE001
                logger.exception("System metrics update failed: %s", exc)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("System metrics collector cancelled")
        raise


@asynccontextmanager
async def lifespan_collector() -> AsyncIterator[None]:
    """Start the collector on enter, cancel on exit. Used as a lifespan sub-step."""
    task = asyncio.create_task(_collect_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.exception("Collector task ended with error: %s", exc)
