import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from adam.config import config
from adam.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("adam")

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"

app = FastAPI(title="Robot Brain API")
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

log.info("Provider: %s  Model: %s", config.llm.provider, config.llm.model)


@app.get("/")
async def serve_frontend():
    return FileResponse(STATIC_DIR / "index.html")


def main():
    uvicorn.run(
        "adam.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        ws_ping_interval=20,
        ws_ping_timeout=15,
    )


if __name__ == "__main__":
    main()
