"""Analytics endpoints — stubs returning 501."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/overview")
async def analytics_overview():
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/recent")
async def analytics_recent():
    raise HTTPException(status_code=501, detail="Not implemented")
