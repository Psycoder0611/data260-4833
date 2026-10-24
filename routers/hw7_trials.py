"""HW7 Part 1: clinical trial routes protected by JWT roles.

reader: list/read only. writer and moderator: create. moderator only: delete.
The old HW4 session routes and the HW5 routes are not changed.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from hw7.db import HW7User
from hw7.deps import get_current_user, require_roles
from hw7.schemas import TrialCreate, TrialOut
from models import ClinicalTrialDB, ResearchOrganizationDB

router = APIRouter(prefix="/api/hw7/trials", tags=["HW7 Clinical Trials (JWT)"])


@router.get("", response_model=list[TrialOut])
def list_trials(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: HW7User = Depends(get_current_user),
) -> list[ClinicalTrialDB]:
    """List trials. Any logged-in role may read."""
    return (
        db.query(ClinicalTrialDB)
        .filter(ClinicalTrialDB.trial_code.isnot(None))
        .order_by(ClinicalTrialDB.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{trial_id}", response_model=TrialOut)
def get_trial(
    trial_id: int,
    db: Session = Depends(get_db),
    current_user: HW7User = Depends(get_current_user),
) -> ClinicalTrialDB:
    """Return one trial. Any logged-in role may read."""
    trial = db.get(ClinicalTrialDB, trial_id)
    if trial is None:
        raise HTTPException(status_code=404, detail="Clinical trial not found")
    return trial


@router.post("", response_model=TrialOut, status_code=201)
def create_trial(
    trial: TrialCreate,
    db: Session = Depends(get_db),
    current_user: HW7User = Depends(require_roles("writer", "moderator")),
) -> ClinicalTrialDB:
    """Create a trial. Only writer or moderator."""
    organization = db.get(ResearchOrganizationDB, trial.organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Research organization not found")

    new_trial = ClinicalTrialDB(
        trialTitle=trial.trialTitle.strip(),
        sponsor=organization.name,
        trial_code=trial.trial_code.strip(),
        participant_capacity=trial.participant_capacity,
        organization_id=trial.organization_id,
    )
    db.add(new_trial)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Trial code already exists"
        ) from exc
    db.refresh(new_trial)
    return new_trial


@router.delete("/{trial_id}")
def delete_trial(
    trial_id: int,
    db: Session = Depends(get_db),
    current_user: HW7User = Depends(require_roles("moderator")),
) -> dict:
    """Delete a trial. Only moderator."""
    trial = db.get(ClinicalTrialDB, trial_id)
    if trial is None:
        raise HTTPException(status_code=404, detail="Clinical trial not found")
    db.delete(trial)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Trial still has related notes"
        ) from exc
    return {
        "message": "Clinical trial deleted successfully",
        "id": trial_id,
        "deleted_by": current_user.username,
    }
