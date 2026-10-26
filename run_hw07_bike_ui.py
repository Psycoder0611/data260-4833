"""HW7 Part 4: small web UI for the Bay Wheels agent.

uvicorn run_hw07_bike_ui:app --port 8334
Fields: CSV upload, pricing URL, Run (plus the rider to analyse).
"""

import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from hw7 import bike_run

app = FastAPI(title="Bay Wheels Plan Advisor (HW7 Part 4)")
PAGE = Path(__file__).parent / "hw7" / "bike_page.html"
JOBS: Dict[str, Dict[str, Any]] = {}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return PAGE.read_text(encoding="utf-8")


def _worker(job: Dict[str, Any], csv_path: str, rider: str, url: str) -> None:
    def keep(event: Dict[str, Any]) -> None:
        job["events"].append(
            {k: v for k, v in event.items() if k != "full_observation"}
        )

    try:
        job["result"] = bike_run.run_scenario(csv_path, rider, url, on_event=keep)
        job["status"] = "done"
    except Exception as exc:  # shown in the page instead of a stack trace
        job["status"] = "error"
        job["error"] = f"{type(exc).__name__}: {exc}"


@app.post("/api/run")
async def run(
    csv: UploadFile = File(...), url: str = Form(...), rider: str = Form(...)
) -> Dict[str, str]:
    name = Path(csv.filename or "uploaded.csv").name
    if not name.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a .csv file")
    if not url.strip() or not rider.strip():
        raise HTTPException(400, "The pricing URL and the rider ID are required")
    folder = Path(tempfile.mkdtemp(prefix="bike_upload_"))
    path = folder / name
    with open(path, "wb") as out:
        shutil.copyfileobj(csv.file, out)
    job_id = uuid.uuid4().hex[:10]
    job: Dict[str, Any] = {"status": "running", "events": [], "result": None}
    JOBS[job_id] = job
    threading.Thread(
        target=_worker, args=(job, str(path), rider.strip(), url.strip()), daemon=True
    ).start()
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
def job_status(job_id: str) -> Dict[str, Any]:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "unknown job")
    return job
