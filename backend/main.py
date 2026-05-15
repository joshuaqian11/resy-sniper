import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from database import Database
from config import load_settings
from resy import ResyClient
from sms import SMSClient
from aws import AWSClient
from scheduler import SnipeScheduler
from routers import targets, settings as settings_router

load_dotenv()
logging.basicConfig(level=logging.INFO)

def create_app(db=None, scheduler=None, aws_client=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Init DB
        _db = db or Database(os.environ.get("DATABASE_PATH", "resy.db"))
        if not db:
            await _db.init()
        app.state.db = _db

        # Init clients from DB settings
        cfg = await load_settings(_db)
        resy_client = ResyClient(cfg.resy_api_key, cfg.resy_auth_token)
        sms_client = SMSClient(
            cfg.twilio_account_sid, cfg.twilio_auth_token,
            cfg.twilio_from, cfg.phone_number,
        )
        if aws_client:
            _aws = aws_client
        else:
            instance_id = AWSClient.get_instance_id()
            _aws = AWSClient(region="us-east-1", instance_id=instance_id)
            _aws.instance_id = instance_id
        app.state.aws_client = _aws

        # Init scheduler
        _scheduler = scheduler or SnipeScheduler(
            db=_db, resy_client=resy_client,
            sms_client=sms_client, aws_client=_aws,
        )
        if not scheduler:
            _scheduler.start()
            await _scheduler.reload_pending()
        app.state.scheduler = _scheduler

        yield

        if not scheduler:
            _scheduler.shutdown()
        if not db:
            await _db.close()

    app = FastAPI(title="Resy Bot", lifespan=lifespan)

    # When all deps are injected (test mode), eagerly set state so requests
    # work even if the ASGI lifespan isn't triggered by the test transport.
    if db is not None and scheduler is not None and aws_client is not None:
        app.state.db = db
        app.state.scheduler = scheduler
        app.state.aws_client = aws_client

    app.include_router(targets.router)
    app.include_router(settings_router.router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    # Serve React build in production
    frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
    if os.path.isdir(frontend_dist):
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")

    return app

app = create_app()
