"""Create the s4833_doc collections with schema validation and indexes (safe to re-run)."""
from pymongo import ASCENDING, DESCENDING

from hw6 import config
from hw6.mongo import get_db

STATUSES = ["recruiting", "active", "completed", "terminated"]
PHASES = ["phase1", "phase2", "phase3", "phase4", "not_applicable"]

VALIDATORS = {
    config.TRIALS_COLLECTION: {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["trialTitle", "status", "phase", "scheduledDate", "createdAt", "updatedAt"],
            "properties": {
                "trialTitle": {"bsonType": "string", "minLength": 1, "maxLength": 100},
                "description": {"bsonType": ["string", "null"]},
                "status": {"enum": STATUSES},
                "phase": {"enum": PHASES},
                "scheduledDate": {"bsonType": "date"},
                "createdAt": {"bsonType": "date"},
                "updatedAt": {"bsonType": "date"},
            },
        }
    },
    config.MESSAGES_COLLECTION: {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["user_id", "session_id", "role", "content", "created_at"],
            "properties": {
                "user_id": {"bsonType": "string"},
                "session_id": {"bsonType": "string"},
                "role": {"enum": ["user", "assistant"]},
                "content": {"bsonType": "string"},
                "created_at": {"bsonType": "date"},
            },
        }
    },
    config.SUMMARIES_COLLECTION: {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["user_id", "session_id", "scope", "text", "created_at"],
            "properties": {
                "user_id": {"bsonType": "string"},
                "session_id": {"bsonType": ["string", "null"]},
                "scope": {"enum": ["session", "user"]},
                "text": {"bsonType": "string"},
                "created_at": {"bsonType": "date"},
            },
        }
    },
    config.EPISODES_COLLECTION: {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["user_id", "session_id", "fact", "importance", "embedding", "created_at"],
            "properties": {
                "user_id": {"bsonType": "string"},
                "session_id": {"bsonType": "string"},
                "fact": {"bsonType": "string"},
                "importance": {"bsonType": "number", "minimum": 0, "maximum": 1},
                "embedding": {"bsonType": "array"},
                "created_at": {"bsonType": "date"},
            },
        }
    },
}

INDEXES = {
    config.TRIALS_COLLECTION: [[("createdAt", DESCENDING)], [("status", ASCENDING), ("phase", ASCENDING)]],
    config.MESSAGES_COLLECTION: [[("user_id", ASCENDING), ("session_id", ASCENDING), ("created_at", ASCENDING)]],
    config.SUMMARIES_COLLECTION: [[("user_id", ASCENDING), ("scope", ASCENDING), ("created_at", DESCENDING)]],
    config.EPISODES_COLLECTION: [[("user_id", ASCENDING), ("created_at", DESCENDING)]],
}


def setup_database(only: str = "all") -> None:
    """Create or update collections. only is 'trials', 'memory' or 'all'."""
    database = get_db()
    existing = set(database.list_collection_names())
    memory_names = {
        config.MESSAGES_COLLECTION,
        config.SUMMARIES_COLLECTION,
        config.EPISODES_COLLECTION,
    }
    for name, validator in VALIDATORS.items():
        if only == "trials" and name != config.TRIALS_COLLECTION:
            continue
        if only == "memory" and name not in memory_names:
            continue
        if name in existing:
            database.command("collMod", name, validator=validator, validationAction="error")
            action = "updated"
        else:
            database.create_collection(name, validator=validator, validationAction="error")
            action = "created"
        for keys in INDEXES[name]:
            database[name].create_index(keys)
        print(f"{config.MONGODB_DB}.{name}: {action} with validation and indexes")


if __name__ == "__main__":
    import sys

    setup_database(sys.argv[1] if len(sys.argv) > 1 else "all")
