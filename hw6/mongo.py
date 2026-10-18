"""PyMongo connection helpers (one shared client for the whole app)."""
from typing import Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from hw6 import config

_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    """Return the shared MongoClient, creating it on first use."""
    global _client
    if _client is None:
        _client = MongoClient(
            config.MONGODB_URI,
            tz_aware=True,
            serverSelectionTimeoutMS=3000,
        )
    return _client


def use_client(client: MongoClient) -> None:
    """Replace the shared client (used by offline tests)."""
    global _client
    _client = client


def get_db() -> Database:
    """Return the s4833_doc database."""
    return get_client()[config.MONGODB_DB]


def get_collection(name: str) -> Collection:
    """Return one collection from the s4833_doc database."""
    return get_db()[name]


def ping() -> bool:
    """Return True when MongoDB answers a ping."""
    get_client().admin.command("ping")
    return True
