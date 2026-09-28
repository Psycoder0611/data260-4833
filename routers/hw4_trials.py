from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models import ClinicalTrialDB, TrialNoteDB, UserDB
from routers.hw4_auth import get_current_user


router = APIRouter(
    prefix="/api/hw4/trials",
    tags=["HW4 Clinical Trials"]
)


class TrialCreate(BaseModel):
    trialTitle: str
    sponsor: str


class TrialUpdate(BaseModel):
    trialTitle: str
    sponsor: str


class TrialResponse(BaseModel):
    id: int
    trialTitle: str
    sponsor: str

    model_config = {
        "from_attributes": True
    }


class TrialNoteResponse(BaseModel):
    id: int
    trial_id: int
    note: str

    model_config = {
        "from_attributes": True
    }


class TrialWithNotesResponse(BaseModel):
    id: int
    trialTitle: str
    sponsor: str
    notes: list[TrialNoteResponse]


@router.post(
    "",
    response_model=TrialResponse,
    status_code=201
)
def create_trial(
    trial: TrialCreate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    new_trial = ClinicalTrialDB(
        trialTitle=trial.trialTitle.strip(),
        sponsor=trial.sponsor.strip()
    )

    db.add(new_trial)
    db.commit()
    db.refresh(new_trial)

    return new_trial


@router.get(
    "",
    response_model=list[TrialResponse]
)
def get_trials(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    return (
        db.query(ClinicalTrialDB)
        .order_by(ClinicalTrialDB.id)
        .all()
    )


@router.get(
    "/naive",
    response_model=list[TrialWithNotesResponse]
)
def get_trials_naive(
    page_size: int = Query(
        default=10,
        ge=1,
        le=200
    ),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    trials = (
        db.query(ClinicalTrialDB)
        .order_by(ClinicalTrialDB.id)
        .limit(page_size)
        .all()
    )

    results = []

    for trial in trials:
        notes = (
            db.query(TrialNoteDB)
            .filter(TrialNoteDB.trial_id == trial.id)
            .all()
        )

        results.append(
            {
                "id": trial.id,
                "trialTitle": trial.trialTitle,
                "sponsor": trial.sponsor,
                "notes": notes
            }
        )

    return results


@router.get(
    "/fixed",
    response_model=list[TrialWithNotesResponse]
)
def get_trials_fixed(
    page_size: int = Query(
        default=10,
        ge=1,
        le=200
    ),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    trials = (
        db.query(ClinicalTrialDB)
        .options(
            selectinload(ClinicalTrialDB.notes)
        )
        .order_by(ClinicalTrialDB.id)
        .limit(page_size)
        .all()
    )

    results = []

    for trial in trials:
        results.append(
            {
                "id": trial.id,
                "trialTitle": trial.trialTitle,
                "sponsor": trial.sponsor,
                "notes": trial.notes
            }
        )

    return results


@router.get(
    "/{trial_id}",
    response_model=TrialResponse
)
def get_trial(
    trial_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    trial = db.get(ClinicalTrialDB, trial_id)

    if trial is None:
        raise HTTPException(
            status_code=404,
            detail="Clinical trial not found"
        )

    return trial


@router.put(
    "/{trial_id}",
    response_model=TrialResponse
)
def update_trial(
    trial_id: int,
    trial_data: TrialUpdate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    trial = db.get(ClinicalTrialDB, trial_id)

    if trial is None:
        raise HTTPException(
            status_code=404,
            detail="Clinical trial not found"
        )

    trial.trialTitle = trial_data.trialTitle.strip()
    trial.sponsor = trial_data.sponsor.strip()

    db.commit()
    db.refresh(trial)

    return trial


@router.delete("/{trial_id}")
def delete_trial(
    trial_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user)
):
    trial = db.get(ClinicalTrialDB, trial_id)

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