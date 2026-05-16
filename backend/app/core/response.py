from __future__ import annotations

from typing import Optional

from typing import Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: Optional[T] = None
    trace_id: str = Field(default_factory=lambda: f"trace_{uuid4().hex[:12]}")


def success(data: Optional[T] = None, message: str = "success") -> ApiResponse[T]:
    return ApiResponse[T](message=message, data=data)
