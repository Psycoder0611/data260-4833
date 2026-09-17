from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_302_FOUND
import time


# Create a router object
# This behaves like a mini FastAPI app
router = APIRouter()

# Configure Jinja2 templates directory
templates = Jinja2Templates(directory="templates")


# Hardcoded credentials for demo purposes only
# In real applications, credentials come from a database
VALID_USERNAME = "admin"
VALID_PASSWORD = "password"

# Idle timeout used for HW3 demonstration.
# If the user is inactive for more than 60 seconds,
# the session is cleared.
IDLE_TIMEOUT_SECONDS = 60

@router.get("/")
def home(request: Request):
    """
    Home page route.

    - Checks if a user is logged in using the session
    - Passes user info to the template
    """
    user = request.session.get("user")

    return templates.TemplateResponse(
    request=request,
    name="index.html",
    context={
        "user": user
    }
)


@router.get("/login")
def login_page(request: Request):

    user = request.session.get("user")

    expired = request.query_params.get("expired")

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "user": user,
            "expired": expired
        }
    )


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """
    Handles login form submission.

    - Reads username and password from the form
    - Validates credentials
    - Stores user info in session if valid
    """
    if username == VALID_USERNAME and password == VALID_PASSWORD:
        # Store logged-in user in session
        request.session["user"] = username

        request.session["last_activity"] = time.time() #added for timelimit

        # Redirect user to dashboard
        return RedirectResponse(
            url="/dashboard",
            status_code=HTTP_302_FOUND
        )

    # If credentials are invalid:
    # Redirect back to login page
    #
    # NOTE:
    # No error message is shown intentionally.
    # Students are expected to add Bootstrap alerts.
    return templates.TemplateResponse(  #replaced this section...hw3
    request=request,
    name="login.html",
    context={
        "user": None,
        "error": "Invalid username or password."
    },
    status_code=401
)


@router.get("/dashboard")
def dashboard(request: Request):
    """
    Protected dashboard route.

    The user must have a valid session.
    The session also expires after a period of inactivity.
    """

    user = request.session.get("user")
    last_activity = request.session.get("last_activity")

    # No authenticated user -> redirect to login
    if not user:
        return RedirectResponse(
            url="/login",
            status_code=HTTP_302_FOUND
        )

    # Check whether the session has been idle too long
    if last_activity is not None:

        idle_time = time.time() - last_activity

        if idle_time > IDLE_TIMEOUT_SECONDS:

            # Remove all session data after timeout
            request.session.clear()

            return RedirectResponse(
                url="/login?expired=1",
                status_code=HTTP_302_FOUND
            )

    # User is still active, so refresh the last activity time
    request.session["last_activity"] = time.time()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user
        }
    )