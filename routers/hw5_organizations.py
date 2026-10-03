from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models import ResearchOrganizationDB


router = APIRouter(
    prefix="/api/hw5/organizations",
    tags=["HW5 Research Organizations"]
)


# ---------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    country: str = Field(min_length=2, max_length=100)
    contact_email: EmailStr


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    country: str = Field(min_length=2, max_length=100)
    contact_email: EmailStr


class OrganizationResponse(BaseModel):
    id: int
    name: str
    country: str
    contact_email: str
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
    response_model=OrganizationResponse,
    status_code=201
)
def create_organization(
    organization: OrganizationCreate,
    db: Session = Depends(get_db)
):
    new_organization = ResearchOrganizationDB(
        name=organization.name.strip(),
        country=organization.country.strip(),
        contact_email=str(
            organization.contact_email
        ).lower()
    )

    db.add(new_organization)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Organization contact email already exists"
        )

    db.refresh(new_organization)

    return new_organization


# ---------------------------------------------------------
# LIST WITH PAGINATION
# ---------------------------------------------------------

@router.get(
    "",
    response_model=list[OrganizationResponse]
)
def list_organizations(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    return (
        db.query(ResearchOrganizationDB)
        .order_by(ResearchOrganizationDB.id)
        .offset(skip)
        .limit(limit)
        .all()
    )

# ---------------------------------------------------------
# RELATIONSHIP QUERY
# Get all clinical trials for one organization
# ---------------------------------------------------------

@router.get(
    "/{organization_id}/trials"
)
def get_organization_trials(
    organization_id: int,
    db: Session = Depends(get_db)
):
    # First, check whether the organization exists.
    organization = db.get(
        ResearchOrganizationDB,
        organization_id
    )

    if organization is None:
        raise HTTPException(
            status_code=404,
            detail="Research organization not found"
        )

    # Return all clinical trials linked to this organization.
    return [
        {
            "id": trial.id,
            "trialTitle": trial.trialTitle,
            "trial_code": trial.trial_code,
            "participant_capacity": trial.participant_capacity,
            "organization_id": trial.organization_id
        }
        for trial in organization.trials
    ]

# ---------------------------------------------------------
# GET BY ID
# ---------------------------------------------------------

@router.get(
    "/{organization_id}",
    response_model=OrganizationResponse
)
def get_organization(
    organization_id: int,
    db: Session = Depends(get_db)
):
    organization = db.get(
        ResearchOrganizationDB,
        organization_id
    )

    if organization is None:
        raise HTTPException(
            status_code=404,
            detail="Research organization not found"
        )

    return organization


# ---------------------------------------------------------
# UPDATE
# ---------------------------------------------------------

@router.put(
    "/{organization_id}",
    response_model=OrganizationResponse
)
def update_organization(
    organization_id: int,
    organization_data: OrganizationUpdate,
    db: Session = Depends(get_db)
):
    organization = db.get(
        ResearchOrganizationDB,
        organization_id
    )

    if organization is None:
        raise HTTPException(
            status_code=404,
            detail="Research organization not found"
        )

    organization.name = (
        organization_data.name.strip()
    )

    organization.country = (
        organization_data.country.strip()
    )

    organization.contact_email = str(
        organization_data.contact_email
    ).lower()

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Organization contact email already exists"
        )

    db.refresh(organization)

    return organization


# ---------------------------------------------------------
# DELETE
# ---------------------------------------------------------

@router.delete(
    "/{organization_id}"
)
def delete_organization(
    organization_id: int,
    db: Session = Depends(get_db)
):
    organization = db.get(
        ResearchOrganizationDB,
        organization_id
    )

    if organization is None:
        raise HTTPException(
            status_code=404,
            detail="Research organization not found"
        )

    if organization.trials:
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete organization because "
                "clinical trials are associated with it"
            )
        )

    db.delete(organization)
    db.commit()

    return {
        "message": (
            "Research organization deleted successfully"
        ),
        "id": organization_id
    }