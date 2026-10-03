from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import ClinicalTrialDB, ResearchOrganizationDB


router = APIRouter(
    prefix="/api/hw5/trials",
    tags=["HW5 Clinical Trials"]
)


# ---------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------

class HW5TrialCreate(BaseModel):
    trialTitle: str = Field(
        min_length=2,
        max_length=255
    )

    trial_code: str = Field(
        min_length=3,
        max_length=100
    )

    participant_capacity: int = Field(
        default=100,
        ge=1
    )

    organization_id: int = Field(
        ge=1
    )


class HW5TrialUpdate(BaseModel):
    trialTitle: str = Field(
        min_length=2,
        max_length=255
    )

    trial_code: str = Field(
        min_length=3,
        max_length=100
    )

    participant_capacity: int = Field(
        ge=1
    )

    organization_id: int = Field(
        ge=1
    )


class HW5TrialResponse(BaseModel):
    id: int
    trialTitle: str
    sponsor: str
    trial_code: str | None
    participant_capacity: int
    organization_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }


# ---------------------------------------------------------
# CREATE
# ---------------------------------------------------------

@router.post(
    "",
    response_model=HW5TrialResponse,
    status_code=201
)
def create_trial(
    trial: HW5TrialCreate,
    db: Session = Depends(get_db)
):
    organization = db.get(
        ResearchOrganizationDB,
        trial.organization_id
    )

    if organization is None:
        raise HTTPException(
            status_code=404,
            detail="Research organization not found"
        )

    new_trial = ClinicalTrialDB(
        trialTitle=trial.trialTitle.strip(),
        sponsor=organization.name,
        trial_code=trial.trial_code.strip(),
        participant_capacity=trial.participant_capacity,
        organization_id=trial.organization_id
    )

    db.add(new_trial)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Trial code already exists"
        )

    db.refresh(new_trial)

    return new_trial


# ---------------------------------------------------------
# LIST
# ---------------------------------------------------------

@router.get(
    "",
    response_model=list[HW5TrialResponse]
)
def list_trials(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    return (
        db.query(ClinicalTrialDB)
        .filter(
            ClinicalTrialDB.trial_code.isnot(None)
        )
        .order_by(ClinicalTrialDB.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------
# GET BY ID
# ---------------------------------------------------------

@router.get(
    "/{trial_id}",
    response_model=HW5TrialResponse
)
def get_trial(
    trial_id: int,
    db: Session = Depends(get_db)
):
    trial = db.get(
        ClinicalTrialDB,
        trial_id
    )

    if trial is None:
        raise HTTPException(
            status_code=404,
            detail="Clinical trial not found"
        )

    return trial


# ---------------------------------------------------------
# UPDATE
# ---------------------------------------------------------

@router.put(
    "/{trial_id}",
    response_model=HW5TrialResponse
)
def update_trial(
    trial_id: int,
    trial_data: HW5TrialUpdate,
    db: Session = Depends(get_db)
):
    trial = db.get(
        ClinicalTrialDB,
        trial_id
    )

    if trial is None:
        raise HTTPException(
            status_code=404,
            detail="Clinical trial not found"
        )

    organization = db.get(
        ResearchOrganizationDB,
        trial_data.organization_id
    )

    if organization is None:
        raise HTTPException(
            status_code=404,
            detail="Research organization not found"
        )

    trial.trialTitle = (
        trial_data.trialTitle.strip()
    )

    trial.trial_code = (
        trial_data.trial_code.strip()
    )

    trial.participant_capacity = (
        trial_data.participant_capacity
    )

    trial.organization_id = (
        trial_data.organization_id
    )

    # Keep the old HW4 sponsor field synchronized.
    trial.sponsor = organization.name

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Trial code already exists"
        )

    db.refresh(trial)

    return trial


# ---------------------------------------------------------
# DELETE
# ---------------------------------------------------------

@router.delete(
    "/{trial_id}"
)
def delete_trial(
    trial_id: int,
    db: Session = Depends(get_db)
):
    trial = db.get(
        ClinicalTrialDB,
        trial_id
    )

    if trial is None:
        raise HTTPException(
            status_code=404,
            detail="Clinical trial not found"
        )

    db.delete(trial)
    db.commit()

    return {
        "message": "Clinical trial deleted successfully",
        "id": trial_id
    }