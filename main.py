from fastapi.middleware.cors import CORSMiddleware #hw4%
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import uvicorn
import os
from starlette.middleware.sessions import SessionMiddleware  #extension of hw3
from routers.auth import router as auth_router
from routers.hw4_auth import router as hw4_auth_router # adding for hw4
from routers.hw4_trials import router as hw4_trials_router #adding for hw4
from routers.hw5_organizations import router as hw5_organizations_router
from routers.hw5_trials import router as hw5_trials_router


# I am creating one FastAPI application for my Clinical Trial Listings domain.
app = FastAPI(
    title="Clinical Trial Listings API",
    version="2.0.0"
)
app.add_middleware(  #added hw4
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret-key")

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=True,
    same_site="lax",
    max_age=3600
)

app.include_router(auth_router)
app.include_router(hw4_auth_router) # adding for hw4
app.include_router(hw4_trials_router) # adding for hw4
app.include_router(hw5_organizations_router)
app.include_router(hw5_trials_router)
# ---------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------

# This model represents one complete clinical trial record.
class ClinicalTrial(BaseModel):
    id: int
    trialTitle: str
    sponsor: str
    submitterEmail: str
    description: str
    category: str


# I am using a separate model for creating a new record
# because the user does not provide the ID manually.
class ClinicalTrialCreate(BaseModel):
    trialTitle: str
    sponsor: str
    submitterEmail: str
    description: str
    category: str


# I am using this model when updating an existing record.
class ClinicalTrialUpdate(BaseModel):
    trialTitle: str
    sponsor: str
    submitterEmail: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None


# ---------------------------------------------------------
# In-memory data
# ---------------------------------------------------------

# I am starting with a few sample clinical trial records
# so the list is not empty when the application first runs.
clinical_trials: List[ClinicalTrial] = [

    ClinicalTrial(
        id=1,
        trialTitle="Diabetes Prevention Study",
        sponsor="Stanford Medicine",
        submitterEmail="research@stanford.edu",
        description=(
            "A clinical study evaluating lifestyle and treatment "
            "approaches for preventing type 2 diabetes."
        ),
        category="Behavioral Study"
    ),

    ClinicalTrial(
        id=2,
        trialTitle="Hypertension Drug Trial",
        sponsor="Bay Area Medical Research",
        submitterEmail="trials@bayresearch.org",
        description=(
            "A study evaluating the effectiveness of a new medication "
            "for adults with hypertension."
        ),
        category="Drug Trial"
    ),

    ClinicalTrial(
        id=3,
        trialTitle="Respiratory Vaccine Study",
        sponsor="California Health Institute",
        submitterEmail="research@chi.org",
        description=(
            "A vaccine trial studying immune response and safety "
            "in adult participants."
        ),
        category="Vaccine Trial"
    ),
]


# ---------------------------------------------------------
# Home page
# ---------------------------------------------------------

# I am serving my existing HW1 HTML file through FastAPI.
@app.get("/trials")   #changed from "/" to "/trials" for hw3
async def home():
    return FileResponse("index.html")


# I am serving the JavaScript file separately
# because index.html loads script.js.
@app.get("/script.js")
async def javascript_file():
    return FileResponse(
        "script.js",
        media_type="application/javascript"
    )


# ---------------------------------------------------------
# GET records + search
# ---------------------------------------------------------

@app.get(
    "/api/trials",
    response_model=List[ClinicalTrial]
)
async def get_trials(
    q: Optional[str] = Query(
        default=None,
        description="Search by trial title or sponsor"
    )
):
    """
    I am returning all clinical trial records.

    If q is provided, I am filtering the list using
    the primary field (trialTitle) or secondary field (sponsor).
    """

    # If there is no search value, I return the full list.
    if not q or not q.strip():
        return clinical_trials

    search_value = q.strip().lower()

    # I am using case-insensitive partial matching.
    matching_trials = [
        trial
        for trial in clinical_trials
        if search_value in trial.trialTitle.lower()
        or search_value in trial.sponsor.lower()
    ]

    return matching_trials


# ---------------------------------------------------------
# CREATE
# HW2 Part 2, Question 1
# ---------------------------------------------------------

@app.post(
    "/api/trials",
    response_model=ClinicalTrial,
    status_code=201
)
async def create_trial(
    trial_data: ClinicalTrialCreate
):
    """
    I am adding a new clinical trial record.

    The new ID is always one greater than the current
    highest ID.
    """

    # I am checking the two main domain fields manually
    # so whitespace-only values are not accepted.
    if not trial_data.trialTitle.strip():
        raise HTTPException(
            status_code=400,
            detail="Clinical trial title is required."
        )

    if not trial_data.sponsor.strip():
        raise HTTPException(
            status_code=400,
            detail="Sponsor or institution is required."
        )

    # I am finding the current highest ID.
    highest_id = max(
        (trial.id for trial in clinical_trials),
        default=0
    )

    new_trial = ClinicalTrial(
        id=highest_id + 1,
        trialTitle=trial_data.trialTitle.strip(),
        sponsor=trial_data.sponsor.strip(),
        submitterEmail=trial_data.submitterEmail.strip(),
        description=trial_data.description.strip(),
        category=trial_data.category
    )

    clinical_trials.append(new_trial)

    print(f"Created clinical trial: {new_trial}")

    return new_trial


# ---------------------------------------------------------
# UPDATE
# HW2 Part 2, Question 2
# ---------------------------------------------------------

@app.put(
    "/api/trials/{trial_id}",
    response_model=ClinicalTrial
)
async def update_trial(
    trial_id: int,
    trial_data: ClinicalTrialUpdate
):
    """
    I am updating an existing clinical trial record.

    For the HW2 screenshot, I will specifically update ID 1.
    """

    trial = next(
        (
            trial
            for trial in clinical_trials
            if trial.id == trial_id
        ),
        None
    )

    if trial is None:
        raise HTTPException(
            status_code=404,
            detail="Clinical trial not found."
        )

    if not trial_data.trialTitle.strip():
        raise HTTPException(
            status_code=400,
            detail="Clinical trial title is required."
        )

    if not trial_data.sponsor.strip():
        raise HTTPException(
            status_code=400,
            detail="Sponsor or institution is required."
        )

    # The assignment specifically requires updating
    # the primary and secondary domain fields.
    trial.trialTitle = trial_data.trialTitle.strip()
    trial.sponsor = trial_data.sponsor.strip()

    # I am also allowing the additional HW1 fields
    # to be updated when values are provided.
    if trial_data.submitterEmail is not None:
        trial.submitterEmail = (
            trial_data.submitterEmail.strip()
        )

    if trial_data.description is not None:
        trial.description = (
            trial_data.description.strip()
        )

    if trial_data.category is not None:
        trial.category = trial_data.category

    print(f"Updated clinical trial: {trial}")

    return trial


# ---------------------------------------------------------
# DELETE
# ---------------------------------------------------------

@app.delete(
    "/api/trials/{trial_id}",
    status_code=204
)
async def delete_trial(
    trial_id: int
):
    """
    I am deleting a clinical trial using its ID.

    The frontend will find the highest ID first and
    send that ID to this endpoint.
    """

    trial_index = next(
        (
            index
            for index, trial in enumerate(clinical_trials)
            if trial.id == trial_id
        ),
        None
    )

    if trial_index is None:
        raise HTTPException(
            status_code=404,
            detail="Clinical trial not found."
        )

    deleted_trial = clinical_trials.pop(
        trial_index
    )

    print(
        f"Deleted clinical trial: {deleted_trial}"
    )

    return None


# ---------------------------------------------------------
# Start server
# ---------------------------------------------------------

if __name__ == "__main__":

    # PORT_BASE for SID4 = 4833:
    # 8000 + (4833 mod 900) = 8333
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8333
    )