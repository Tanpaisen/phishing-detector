import os
import secrets
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

load_dotenv(Path(__file__).with_name(".env"))

SERVICE_TOKEN = os.getenv("AI_SERVICE_TOKEN", "")

if len(SERVICE_TOKEN) < 32:
    raise RuntimeError("AI_SERVICE_TOKEN chưa được cấu hình hợp lệ.")


def verify_service_token(
    token: Annotated[
        str | None,
        Header(alias="X-Service-Token")
    ] = None,
) -> None:
    if token is None or not secrets.compare_digest(
        token.encode("utf-8"),
        SERVICE_TOKEN.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=401,
            detail="Không được phép truy cập AI Service.",
        )


app = FastAPI(
    title="Phishing Detector AI Service",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    dependencies=[Depends(verify_service_token)],
)


@app.get("/internal/v1/health")
def health():
    return {
        "status": "ok",
        "service": "phishing-detector-ai",
        "model_loaded": False,
    }


@app.get("/internal/v1/ready")
def ready():
    return JSONResponse(
        status_code=503,
        content={
            "status": "not_ready",
            "reason": "MODEL_NOT_LOADED",
        },
    )