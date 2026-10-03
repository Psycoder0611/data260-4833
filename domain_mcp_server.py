import json
import logging
import sys
from typing import Any

from mcp.server import MCPServer
from sqlalchemy.orm import Session

from database import db_session_basede26
from models import ClinicalTrialDB, ResearchOrganizationDB


# ---------------------------------------------------------
# MCP SERVER CONFIGURATION
# ---------------------------------------------------------

mcp = MCPServer("clinical_trials")


# STDIO servers must log to stderr, never stdout.
logger = logging.getLogger("domain_mcp_server")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s"
)
handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(handler)


# ---------------------------------------------------------
# COMMON RESPONSE ENVELOPE
# ---------------------------------------------------------

def success_response(data: Any):
    return {
        "ok": True,
        "data": data,
        "error": None,
    }


def error_response(message: str):
    return {
        "ok": False,
        "data": None,
        "error": message,
    }


# ---------------------------------------------------------
# TOOL 1
# Search clinical trials
# ---------------------------------------------------------

@mcp.tool()
def search_trials(
    query: str,
    limit: int = 10
):
    """
    Search HW5 clinical trials by title or trial code.
    """

    query = query.strip()

    if not query:
        return error_response(
            "query must not be empty"
        )

    if limit < 1 or limit > 25:
        return error_response(
            "limit must be between 1 and 25"
        )

    db: Session = db_session_basede26()

    try:
        pattern = f"%{query}%"

        trials = (
            db.query(ClinicalTrialDB)
            .filter(
                ClinicalTrialDB.trial_code.isnot(None)
            )
            .filter(
                (
                    ClinicalTrialDB.trialTitle.ilike(pattern)
                )
                |
                (
                    ClinicalTrialDB.trial_code.ilike(pattern)
                )
            )
            .order_by(ClinicalTrialDB.id)
            .limit(limit)
            .all()
        )

        data = [
            {
                "id": trial.id,
                "trialTitle": trial.trialTitle,
                "trial_code": trial.trial_code,
                "participant_capacity":
                    trial.participant_capacity,
                "organization_id":
                    trial.organization_id,
            }
            for trial in trials
        ]

        return success_response(data)

    except Exception as exc:
        logger.error(
            "search_trials failed: %s",
            exc
        )

        return error_response(
            "Unable to search clinical trials"
        )

    finally:
        db.close()


# ---------------------------------------------------------
# TOOL 2
# Clinical trial detail lookup
# ---------------------------------------------------------

@mcp.tool()
def get_trial_details(
    trial_id: int
):
    """
    Return one HW5 clinical trial by ID.
    """

    if trial_id < 1:
        return error_response(
            "trial_id must be a positive integer"
        )

    db: Session = db_session_basede26()

    try:
        trial = db.get(
            ClinicalTrialDB,
            trial_id
        )

        if (
            trial is None
            or trial.trial_code is None
        ):
            return error_response(
                "Clinical trial not found"
            )

        organization_name = None

        if trial.organization_id is not None:
            organization = db.get(
                ResearchOrganizationDB,
                trial.organization_id
            )

            if organization is not None:
                organization_name = (
                    organization.name
                )

        data = {
            "id": trial.id,
            "trialTitle": trial.trialTitle,
            "trial_code": trial.trial_code,
            "participant_capacity":
                trial.participant_capacity,
            "organization_id":
                trial.organization_id,
            "organization_name":
                organization_name,
            "created_at": (
                trial.created_at.isoformat()
                if trial.created_at
                else None
            ),
            "updated_at": (
                trial.updated_at.isoformat()
                if trial.updated_at
                else None
            ),
        }

        return success_response(data)

    except Exception as exc:
        logger.error(
            "get_trial_details failed: %s",
            exc
        )

        return error_response(
            "Unable to retrieve clinical trial"
        )

    finally:
        db.close()


# ---------------------------------------------------------
# TOOL 3
# Aggregate clinical trial summary by organization
# ---------------------------------------------------------

@mcp.tool()
def organization_trial_summary(
    organization_id: int
):
    """
    Return aggregate trial information for one organization.
    """

    if organization_id < 1:
        return error_response(
            "organization_id must be a positive integer"
        )

    db: Session = db_session_basede26()

    try:
        organization = db.get(
            ResearchOrganizationDB,
            organization_id
        )

        if organization is None:
            return error_response(
                "Research organization not found"
            )

        trials = [
            trial
            for trial in organization.trials
            if trial.trial_code is not None
        ]

        total_capacity = sum(
            trial.participant_capacity or 0
            for trial in trials
        )

        trial_count = len(trials)

        average_capacity = (
            total_capacity / trial_count
            if trial_count > 0
            else 0
        )

        data = {
            "organization_id":
                organization.id,
            "organization_name":
                organization.name,
            "trial_count":
                trial_count,
            "total_participant_capacity":
                total_capacity,
            "average_participant_capacity":
                round(average_capacity, 2),
        }

        return success_response(data)

    except Exception as exc:
        logger.error(
            "organization_trial_summary failed: %s",
            exc
        )

        return error_response(
            "Unable to calculate organization summary"
        )

    finally:
        db.close()


# ---------------------------------------------------------
# SERVER ENTRY POINT
# ---------------------------------------------------------

if __name__ == "__main__":
    logger.info(
        "Starting Clinical Trials domain MCP server"
    )
    mcp.run()