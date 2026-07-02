"""Sample business endpoints for metrics collection."""

from __future__ import annotations

import uuid
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Deque, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter(prefix="/data", tags=["data"])


class DataItem(BaseModel):
    """Payload accepted by POST /data."""

    payload: dict = Field(default_factory=dict, description="Arbitrary JSON object")
    note: Optional[str] = Field(default=None, description="Optional free-text note")


class DataItemResponse(BaseModel):
    id: str
    received: DataItem
    size: int
    created_at: str


# Bounded thread-safe in-memory store
_store: Deque[DataItemResponse] = deque(maxlen=settings.max_data_items)
_lock = Lock()


@router.post("", response_model=DataItemResponse, status_code=201, summary="Create a data item")
async def create_data(item: DataItem = Body(...)) -> DataItemResponse:
    """Store an incoming JSON payload in the in-memory list."""
    raw = item.model_dump_json().encode("utf-8")
    record = DataItemResponse(
        id=str(uuid.uuid4()),
        received=item,
        size=len(raw),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    with _lock:
        _store.append(record)
    return record


@router.get("", response_model=List[DataItemResponse], summary="List data items")
async def list_data(
    limit: int = Query(default=100, ge=1, le=1000, description="Max items to return"),
    offset: int = Query(default=0, ge=0, description="Items to skip from start"),
) -> List[DataItemResponse]:
    """Return stored data items with optional pagination."""
    with _lock:
        snapshot = list(_store)

    if offset >= len(snapshot):
        return []

    end = offset + limit
    return snapshot[offset:end]


@router.get("/count", summary="Count of items currently in store")
async def count_data() -> dict:
    """Return the current size of the in-memory store."""
    with _lock:
        return {"count": len(_store), "max": _store.maxlen}