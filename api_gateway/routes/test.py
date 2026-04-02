from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, status, Depends


router = APIRouter()


@router.get("/test", status_code=status.HTTP_201_CREATED)
async def test():
    return "hello"

