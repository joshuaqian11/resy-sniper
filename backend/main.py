from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Resy Bot")

@app.get("/api/health")
async def health():
    return {"status": "ok"}
