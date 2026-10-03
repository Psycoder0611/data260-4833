import json
from typing import Callable, Dict, Any

from database import db_session_basede26
from models import ClinicalTrialDB, ResearchOrganizationDB


# ---------------------------------------------------------
# COMMON RESPONSE ENVELOPE
# ---------------------------------------------------------

def success_response(data):
    return {
        "ok": True,
        "data": data,
        "error": None,
    }


def error_response(message):
    return {
        "ok": False,
        "data": None,
        "error": message,
    }


# ---------------------------------------------------------
# DOMAIN TOOL IMPLEMENTATIONS
# ---------------------------------------------------------

def search_trials_tool(inputs):
    query = str(
        inputs.get("query", "")
    ).strip()

    limit = inputs.get("limit", 10)

    if not query:
        return error_response(
            "query must not be empty"
        )

    if (
        not isinstance(limit, int)
        or limit < 1
        or limit > 25
    ):
        return error_response(
            "limit must be between 1 and 25"
        )

    db = db_session_basede26()

    try:
        pattern = f"%{query}%"

        trials = (
            db.query(ClinicalTrialDB)
            .filter(
                ClinicalTrialDB.trial_code.isnot(None)
            )
            .filter(
                ClinicalTrialDB.trialTitle.ilike(pattern)
                |
                ClinicalTrialDB.trial_code.ilike(pattern)
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

    except Exception:
        return error_response(
            "Unable to search clinical trials"
        )

    finally:
        db.close()


def get_trial_details_tool(inputs):
    trial_id = inputs.get("trial_id")

    if (
        not isinstance(trial_id, int)
        or trial_id < 1
    ):
        return error_response(
            "trial_id must be a positive integer"
        )

    db = db_session_basede26()

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

        if trial.organization_id:
            organization = db.get(
                ResearchOrganizationDB,
                trial.organization_id
            )

            if organization:
                organization_name = (
                    organization.name
                )

        return success_response(
            {
                "id": trial.id,
                "trialTitle": trial.trialTitle,
                "trial_code": trial.trial_code,
                "participant_capacity":
                    trial.participant_capacity,
                "organization_id":
                    trial.organization_id,
                "organization_name":
                    organization_name,
            }
        )

    except Exception:
        return error_response(
            "Unable to retrieve clinical trial"
        )

    finally:
        db.close()


def organization_trial_summary_tool(inputs):
    organization_id = inputs.get(
        "organization_id"
    )

    if (
        not isinstance(organization_id, int)
        or organization_id < 1
    ):
        return error_response(
            "organization_id must be a positive integer"
        )

    db = db_session_basede26()

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
            if trial_count
            else 0
        )

        return success_response(
            {
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
        )

    except Exception:
        return error_response(
            "Unable to calculate organization summary"
        )

    finally:
        db.close()


# ---------------------------------------------------------
# DEFAULT TOOL REGISTRY
# ---------------------------------------------------------

DEFAULT_TOOL_REGISTRY = {
    "search_trials":
        search_trials_tool,

    "get_trial_details":
        get_trial_details_tool,

    "organization_trial_summary":
        organization_trial_summary_tool,
}


# ---------------------------------------------------------
# SINGLE SAFE TOOL ENTRY POINT
# ---------------------------------------------------------

def execute_tool(
    name: str,
    inputs: Dict[str, Any],
    tool_registry: Dict[
        str,
        Callable[[dict], dict]
    ] | None = None,
):
    """
    Single entry point for all domain tools.

    Returns a JSON string and never crashes
    on ordinary tool errors.
    """

    registry = (
        tool_registry
        if tool_registry is not None
        else DEFAULT_TOOL_REGISTRY
    )

    try:
        if name not in registry:
            result = error_response(
                f"Unknown tool: {name}"
            )

        elif not isinstance(inputs, dict):
            result = error_response(
                "inputs must be a JSON object"
            )

        elif (
            name == "search_trials"
            and str(
                inputs.get("query", "")
            ).strip() in {"*", "%"}
        ):
            result = error_response(
                "Safety rule: unrestricted wildcard "
                "trial searches are not allowed"
            )

        else:
            result = registry[name](inputs)

        return json.dumps(
            result,
            ensure_ascii=False
        )

    except Exception as exc:
        return json.dumps(
            error_response(
                f"Tool execution failed: {exc}"
            ),
            ensure_ascii=False
        )