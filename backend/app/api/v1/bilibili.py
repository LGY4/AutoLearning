from __future__ import annotations

from fastapi import APIRouter

from app.core.response import ApiResponse, success
from app.services.bilibili_service import search_videos


router = APIRouter()


@router.get("/search/{keyword}", response_model=ApiResponse[dict])
def search_bilibili_get(keyword: str, page: int = 1, page_size: int = 10) -> ApiResponse[dict]:
    return success(search_videos(keyword, page, page_size))
