"""Small helpers shared by the HW6 routes and memory code."""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from bson import ObjectId
from bson.errors import InvalidId


def now_utc() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def is_valid_object_id(value: str) -> bool:
    """Return True when value is a valid MongoDB ObjectId string."""
    try:
        ObjectId(value)
        return True
    except (InvalidId, TypeError):
        return False


def serialize_trial(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a MongoDB trial document into the API response shape."""
    return {
        "id": str(doc["_id"]),
        "trialTitle": doc.get("trialTitle"),
        "description": doc.get("description"),
        "status": doc.get("status"),
        "phase": doc.get("phase"),
        "scheduledDate": doc.get("scheduledDate"),
        "createdAt": doc.get("createdAt"),
        "updatedAt": doc.get("updatedAt"),
    }


def clean_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of a MongoDB document with _id turned into a string id."""
    result = {key: value for key, value in doc.items() if key != "_id"}
    if "_id" in doc:
        result = {"id": str(doc["_id"]), **result}
    return result


def parse_json_array(text: str) -> List[Any]:
    """Pull the first JSON array out of model output; return [] if none is valid."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []
