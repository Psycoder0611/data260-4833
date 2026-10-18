"""HW6 Part 2: chat with MongoDB-backed memory, plus memory and aggregate views."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from hw6 import config, llm, memory
from hw6.schemas import ChatRequest

router = APIRouter(tags=["HW6 Memory (MongoDB)"])

CHAT_PAGE = Path(__file__).resolve().parent.parent / "templates" / "hw6_chat.html"


def mongo_problem(exc: PyMongoError) -> HTTPException:
    """Turn a PyMongo failure into a clear HTTP error."""
    if isinstance(exc, ServerSelectionTimeoutError):
        return HTTPException(503, "MongoDB is not reachable. Is the container running?")
    return HTTPException(500, "Database error while handling the memory request.")


@router.post("/api/chat")
def chat(request: ChatRequest):
    """Save the message, build the memory prompt, call the local model, save the reply."""
    cfg = memory.MemoryConfig()
    if request.short_term_n is not None:
        cfg.short_term_n = request.short_term_n
    if request.memory_policy is not None:
        cfg.policy = request.memory_policy
    try:
        return memory.chat_turn(
            request.user_id,
            request.session_id,
            request.message,
            cfg,
            persist=request.persist,
        )
    except llm.ModelUnavailableError as exc:
        raise HTTPException(503, f"{exc}. Is Ollama running with {config.MODEL_NAME}?")
    except PyMongoError as exc:
        raise mongo_problem(exc)


@router.get("/api/memory/{user_id}")
def memory_view(user_id: str):
    """Return recent messages, latest summaries and recent episodic facts."""
    try:
        return memory.get_memory(user_id)
    except PyMongoError as exc:
        raise mongo_problem(exc)


@router.get("/api/aggregate/{user_id}")
def aggregate_view(user_id: str):
    """Return daily message counts and the most recent summaries."""
    try:
        return memory.get_aggregate(user_id)
    except PyMongoError as exc:
        raise mongo_problem(exc)


@router.get("/hw6/chat", include_in_schema=False)
def chat_page():
    """Serve the small HTML chat page used for screenshots."""
    return FileResponse(CHAT_PAGE)
