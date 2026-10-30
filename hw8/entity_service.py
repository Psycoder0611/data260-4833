"""Business logic for the Clinical Trial entity (Part 1).

No Kafka code lives here. The worker (over Kafka) and the direct JMeter
endpoint both call process_request(), so the only difference between them in
the load test is the Kafka hop.

Entities are kept in a plain dictionary, as the assignment asks.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from hw8 import config

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# field -> (min length, max length) for required text fields
TEXT_FIELDS = {
    "trialTitle": (2, 255),
    "sponsor": (2, 255),
    "trial_code": (3, 100),
    "category": (2, 100),
}
REQUIRED_FIELDS = (
    "trialTitle",
    "sponsor",
    "trial_code",
    "participant_capacity",
    "submitterEmail",
    "category",
)
OPTIONAL_FIELDS = ("description", "organization_id")


def validate_create(data: Any) -> List[str]:
    """Return a list of problems with a create payload (empty list = valid)."""
    if not isinstance(data, dict):
        return ["data must be an object"]
    problems: List[str] = []
    for name in REQUIRED_FIELDS:
        if name not in data or data[name] is None:
            problems.append(f"{name} is required")
    for name, (low, high) in TEXT_FIELDS.items():
        value = data.get(name)
        if value is None:
            continue
        if not isinstance(value, str):
            problems.append(f"{name} must be a string")
        elif not value.strip():
            problems.append(f"{name} must not be empty")
        elif not low <= len(value.strip()) <= high:
            problems.append(f"{name} must be {low} to {high} characters")
    capacity = data.get("participant_capacity")
    if capacity is not None:
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            problems.append("participant_capacity must be an integer")
        elif capacity < 1:
            problems.append("participant_capacity must be at least 1")
    email = data.get("submitterEmail")
    if email is not None:
        if not isinstance(email, str) or not EMAIL_PATTERN.match(email.strip()):
            problems.append("submitterEmail must be a valid email address")
    description = data.get("description")
    if description is not None and (
        not isinstance(description, str) or len(description) > 2000
    ):
        problems.append("description must be a string of at most 2000 characters")
    org = data.get("organization_id")
    if org is not None and (
        isinstance(org, bool) or not isinstance(org, int) or org < 1
    ):
        problems.append("organization_id must be a positive integer")
    return problems


def _clean_entity(data: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only known fields; strip the text fields."""
    entity: Dict[str, Any] = {}
    for name in REQUIRED_FIELDS + OPTIONAL_FIELDS:
        if name in data and data[name] is not None:
            value = data[name]
            entity[name] = value.strip() if isinstance(value, str) else value
    return entity


def create_entity(data: Any, store: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """CREATE: validate, generate a UUID, save in the dictionary, return result."""
    problems = validate_create(data)
    if problems:
        return {"success": False, "error": "Invalid data: " + "; ".join(problems)}
    entity_id = str(uuid.uuid4())
    entity = {
        config.ID_FIELD: entity_id,
        **_clean_entity(data),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    store[entity_id] = entity
    return {
        "success": True,
        config.ID_FIELD: entity_id,
        config.GENERIC_ID_FIELD: entity_id,
        "message": "Clinical trial created",
    }


def get_entity(data: Any, store: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """GET: look up an entity by id; a clean error if it does not exist."""
    if not isinstance(data, dict):
        return {"success": False, "error": "data must be an object"}
    entity_id = data.get(config.ID_FIELD, data.get(config.GENERIC_ID_FIELD))
    if not isinstance(entity_id, str) or not entity_id.strip():
        return {"success": False, "error": f"{config.ID_FIELD} is required"}
    entity = store.get(entity_id.strip())
    if entity is None:
        return {"success": False, "error": "Clinical trial not found"}
    return {
        "success": True,
        "entity": {**entity, config.GENERIC_ID_FIELD: entity[config.ID_FIELD]},
    }


def process_request(
    operation: Any,
    data: Any,
    store: Dict[str, Dict[str, Any]],
    handlers: Optional[Dict[str, Callable[..., Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Run one operation against the store and return the response body.

    Unknown operations get a clean error. The correlation_id is added by the
    caller (worker or API), never here.
    """
    table = handlers or {
        config.CREATE_OPERATION: create_entity,
        config.GET_OPERATION: get_entity,
    }
    handler = table.get(operation) if isinstance(operation, str) else None
    if handler is None:
        return {"success": False, "error": "Unknown operation"}
    return handler(data, store)
