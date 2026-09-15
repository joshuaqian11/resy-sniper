import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from database import Database
from aws import AWSClient
from routers import targets, settings as settings_router, reservations

load_dotenv()
logging.basicConfig(level=logging.INFO)


def create_app(db=None, aws_client=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _db = db or Database(region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
        app.state.db = _db

        lambda_arn = os.environ.get("LAMBDA_ARN", "")
        ec2_instance_id = os.environ.get("EC2_INSTANCE_ID", "")
        _aws = aws_client or AWSClient(
            region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            instance_id=ec2_instance_id,
            lambda_arn=lambda_arn,
        )
        app.state.aws_client = _aws

        _db.complete_past_targets()

        yield

    app = FastAPI(title="Resy Bot", lifespan=lifespan)

    cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if db is not None and aws_client is not None:
        app.state.db = db
        app.state.aws_client = aws_client

    app.include_router(targets.router)
    app.include_router(settings_router.router)
    app.include_router(reservations.router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
    if os.path.isdir(frontend_dist):
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")

    return app


app = create_app()
