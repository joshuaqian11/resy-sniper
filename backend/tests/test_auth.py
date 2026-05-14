import os
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from auth import require_api_key

def make_app():
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(require_api_key)])
    async def protected():
        return {"ok": True}

    return app

def test_missing_header_returns_422():
    os.environ["DASHBOARD_API_KEY"] = "test-key-123"
    client = TestClient(make_app())
    resp = client.get("/protected")
    assert resp.status_code == 422

def test_wrong_key_returns_401():
    os.environ["DASHBOARD_API_KEY"] = "test-key-123"
    client = TestClient(make_app())
    resp = client.get("/protected", headers={"x-api-key": "wrong-key"})
    assert resp.status_code == 401

def test_correct_key_passes():
    os.environ["DASHBOARD_API_KEY"] = "test-key-123"
    client = TestClient(make_app())
    resp = client.get("/protected", headers={"x-api-key": "test-key-123"})
    assert resp.status_code == 200

def test_empty_env_key_rejects_all():
    os.environ.pop("DASHBOARD_API_KEY", None)
    client = TestClient(make_app())
    resp = client.get("/protected", headers={"x-api-key": "any-key"})
    assert resp.status_code == 401
