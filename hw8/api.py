"""FastAPI wrapper for the Kafka request/response service (Part 1) and JMeter.

Run:  uvicorn hw8.api:app --port 8333     (the Docker "api" service does this)

POST /api/hw8/entity         sends the request to Kafka and waits for the reply
POST /api/hw8/entity-direct  runs the same business logic in this process
                             (no Kafka); used as the baseline in the JMeter test

Both take {"operation": "...", "data": {...}}. An optional X-Correlation-ID
header supplies the correlation_id; otherwise one is created once per request.
"""

import json
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from hw8 import config
from hw8.entity_service import process_request
from hw8.logs import get_logger
from hw8.rpc_client import KafkaRPC, RpcTimeout

log = get_logger("FASTAPI")
rpc = KafkaRPC(component="FASTAPI", verbose=config.API_VERBOSE)
direct_store: Dict[str, Dict[str, Any]] = {}


class EntityRequest(BaseModel):
    """Body for both endpoints."""

    operation: str
    data: Dict[str, Any] = Field(default_factory=dict)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Connect to Kafka on start-up and close on shutdown."""
    await rpc.start()
    log.info("FastAPI server started at http://127.0.0.1:%d", config.PORT_BASE)
    log.info(
        "Kafka topics: requests=%s responses=%s",
        config.REQUEST_TOPIC,
        config.RESPONSE_TOPIC,
    )
    yield
    await rpc.stop()
    log.info("FastAPI server stopped")


app = FastAPI(title="HW8 Clinical Trial Kafka Service", lifespan=lifespan)


@app.get("/")
async def home() -> Dict[str, Any]:
    """Health check."""
    return {
        "message": "FastAPI service running",
        "port": config.PORT_BASE,
        "request_topic": config.REQUEST_TOPIC,
        "response_topic": config.RESPONSE_TOPIC,
    }


@app.post("/api/hw8/entity")
async def entity_over_kafka(
    body: EntityRequest,
    x_correlation_id: Optional[str] = Header(default=None),
) -> JSONResponse:
    """Send the operation to the Kafka worker and return its response."""
    correlation_id = x_correlation_id or str(uuid.uuid4())
    try:
        response = await rpc.request(body.operation, body.data, correlation_id)
    except RpcTimeout as exc:
        log.info("TIMEOUT correlation_id=%s", exc.correlation_id)
        return JSONResponse(
            status_code=504,
            content={
                "correlation_id": exc.correlation_id,
                "success": False,
                "error": "Timeout waiting for the Kafka worker",
            },
        )
    if config.API_VERBOSE:
        log.info(
            "RETURNING HTTP response to caller correlation_id=%s: %s",
            correlation_id,
            json.dumps(response),
        )
    return JSONResponse(content=response)


@app.post("/api/hw8/entity-direct")
async def entity_direct(
    body: EntityRequest,
    x_correlation_id: Optional[str] = Header(default=None),
) -> JSONResponse:
    """Run the same operation in this process (no Kafka) for the JMeter baseline."""
    correlation_id = x_correlation_id or str(uuid.uuid4())
    result = process_request(body.operation, body.data, direct_store)
    response = {"correlation_id": correlation_id, "operation": body.operation, **result}
    if config.API_VERBOSE:
        log.info(
            "DIRECT (no Kafka) correlation_id=%s: %s",
            correlation_id,
            json.dumps(response),
        )
    return JSONResponse(content=response)
