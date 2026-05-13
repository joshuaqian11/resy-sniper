import os
from fastapi import Header, HTTPException, status

async def require_api_key(x_api_key: str = Header(...)):
    expected = os.environ.get("DASHBOARD_API_KEY", "")
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
