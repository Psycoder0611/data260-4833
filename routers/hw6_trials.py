"""HW6 Part 1: MongoDB-backed CRUD for clinical trial documents."""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from hw6 import config
from hw6.mongo import get_collection
from hw6.schemas import PhaseEnum, StatusEnum, TrialCreate, TrialOut, TrialUpdate
from hw6.utils import is_valid_object_id, now_utc, serialize_trial
from bson import ObjectId

router = APIRouter(
    prefix="/api/hw6/trials",
    tags=["HW6 Clinical Trials (MongoDB)"],
)


def trials_collection():
    """Return the clinical_trials collection."""
    return get_collection(config.TRIALS_COLLECTION)


def db_error(exc: PyMongoError, action: str) -> HTTPException:
    """Turn a PyMongo failure into a clear HTTP error."""
    if isinstance(exc, ServerSelectionTimeoutError):
        return HTTPException(503, "MongoDB is not reachable. Is the container running?")
    return HTTPException(500, f"Database error while {action}.")


def check_id(trial_id: str) -> None:
    """Raise 400 when the id is not a valid ObjectId."""
    if not is_valid_object_id(trial_id):
        raise HTTPException(400, "Invalid trial id format.")


@router.post("", response_model=TrialOut, status_code=status.HTTP_201_CREATED)
def create_trial(payload: TrialCreate):
    """Create a trial document with automatic createdAt and updatedAt."""
    document = payload.model_dump()
    stamp = now_utc()
    document["createdAt"] = stamp
    document["updatedAt"] = stamp
    try:
        result = trials_collection().insert_one(document)
        created = trials_collection().find_one({"_id": result.inserted_id})
        return serialize_trial(created)
    except PyMongoError as exc:
        raise db_error(exc, "creating the trial")


@router.get("", response_model=List[TrialOut])
def list_trials(
    trial_status: Optional[StatusEnum] = Query(default=None, alias="status"),
    phase: Optional[PhaseEnum] = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    """Return trials, newest first. Optional filters: status, phase."""
    query = {}
    if trial_status:
        query["status"] = trial_status
    if phase:
        query["phase"] = phase
    try:
        cursor = trials_collection().find(query).sort("createdAt", -1).limit(limit)
        return [serialize_trial(doc) for doc in cursor]
    except PyMongoError as exc:
        raise db_error(exc, "listing trials")


@router.get("/{trial_id}", response_model=TrialOut)
def get_trial(trial_id: str):
    """Return one trial by id."""
    check_id(trial_id)
    try:
        doc = trials_collection().find_one({"_id": ObjectId(trial_id)})
    except PyMongoError as exc:
        raise db_error(exc, "reading the trial")
    if doc is None:
        raise HTTPException(404, "Trial not found.")
    return serialize_trial(doc)


@router.put("/{trial_id}", response_model=TrialOut)
def update_trial(trial_id: str, payload: TrialUpdate):
    """Update the fields that were sent and refresh updatedAt."""
    check_id(trial_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "No fields provided to update.")
    changes["updatedAt"] = now_utc()
    try:
        doc = trials_collection().find_one_and_update(
            {"_id": ObjectId(trial_id)},
            {"$set": changes},
            return_document=ReturnDocument.AFTER,
        )
    except PyMongoError as exc:
        raise db_error(exc, "updating the trial")
    if doc is None:
        raise HTTPException(404, "Trial not found.")
    return serialize_trial(doc)


@router.delete("/{trial_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trial(trial_id: str):
    """Delete one trial by id."""
    check_id(trial_id)
    try:
        result = trials_collection().delete_one({"_id": ObjectId(trial_id)})
    except PyMongoError as exc:
        raise db_error(exc, "deleting the trial")
    if result.deleted_count == 0:
        raise HTTPException(404, "Trial not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
