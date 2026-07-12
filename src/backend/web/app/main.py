import json
import os
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from typing import Any

app = FastAPI(title="CalCount Web")
app.add_middleware(SessionMiddleware, secret_key="calcount-dev-secret", https_only=False)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8000")
API_SERVICE_URL = os.getenv("API_SERVICE_URL", "http://api-service:8000")

def authenticate_with_auth_service(email: str, password: str):
    payload = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = UrlRequest(
        f"{AUTH_SERVICE_URL}/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=5) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, {"detail": body}
    except URLError:
        return 502, {"detail": "Authentication service unavailable"}
    
def _call_api(method: str, path: str, token: str | None = None, payload: dict[str, Any] | None = None):
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")

    req = UrlRequest(
        f"{API_SERVICE_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(req, timeout=5) as response:
            response_body = response.read().decode("utf-8")
            return response.status, json.loads(response_body) if response_body else {}
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(response_body)
        except Exception:
            return exc.code, {"detail": response_body}
    except URLError:
        return 502, {"detail": "API service unavailable"}


def create_food_log(token: str, payload: dict[str, Any]):
    return _call_api("POST", "/logs", token=token, payload=payload)


def fetch_logs_for_date(token: str, day: str):
    query = urlencode({"date": day})
    return _call_api("GET", f"/logs?{query}", token=token)


def get_recent_logs_from_api(request: Request) -> list[dict[str, Any]]:
    token = request.session.get("access_token", "")
    if not token:
        return []

    logs: list[dict[str, Any]] = []
    for offset in range(7):
        day = (date.today() - timedelta(days=offset)).isoformat()
        status_code, data = fetch_logs_for_date(token, day)
        if status_code == 200 and isinstance(data, list):
            logs.extend(data)

    logs.sort(key=lambda item: item.get("date", ""), reverse=True)
    return logs[:7]

@app.get("/", include_in_schema=False)
def index(request: Request):
    if request.session.get("user_email"):
        return RedirectResponse("/home", status_code=303)
    return templates.TemplateResponse(request, "index.html", {"request": request})


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if request.session.get("user_email"):
        return RedirectResponse("/home", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"request": request})


@app.post("/login", include_in_schema=False)
async def login_submit(request: Request):
    try:
        payload = await request.json()
    except Exception:
        form = await request.form()
        payload = {
            "email": form.get("email", ""),
            "password": form.get("password", ""),
        }

    email = str(payload.get("email", "")).strip()
    password = str(payload.get("password", "")).strip()

    if not email or not password:
        return JSONResponse(
            {"ok": False, "message": "Please enter your email and password."},
            status_code=400,
        )

    status_code, data = authenticate_with_auth_service(email, password)

    if status_code == 200:
        request.session["user_email"] = email
        request.session["access_token"] = data.get("access_token", "")
        return JSONResponse({"ok": True, "redirect": "/home"})

    message = data.get("detail") if isinstance(data, dict) else str(data)
    return JSONResponse({"ok": False, "message": message}, status_code=status_code)


@app.get("/register", include_in_schema=False)
def register_page(request: Request):
    if request.session.get("user_email"):
        return RedirectResponse("/home", status_code=303)
    return templates.TemplateResponse(request, "register.html", {"request": request})


@app.post("/auth/register", include_in_schema=False)
async def register_submit(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {"ok": False, "message": "Invalid JSON body"},
            status_code=400,
        )

    email = str(payload.get("email", "")).strip()
    password = str(payload.get("password", "")).strip()
    confirm_password = str(payload.get("confirm_password", "")).strip()

    if not email or not password:
        return JSONResponse(
            {"ok": False, "message": "Please fill in all fields."},
            status_code=400,
        )

    if password != confirm_password:
        return JSONResponse(
            {"ok": False, "message": "Passwords do not match."},
            status_code=400,
        )

    request.session["user_email"] = email
    return JSONResponse({"ok": True, "redirect": "/home"})


@app.post("/home/logs", include_in_schema=False)
async def add_log(request: Request):
    if not request.session.get("user_email"):
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    date_value = form.get("date")
    food_name_value = form.get("food_name")

    
    def _as_int(value: Any) -> int:
        if isinstance(value, str):
            return int(value) if value.strip() else 0
        if isinstance(value, (int, float)):
            return int(value)
        return 0

    payload = {
        "date": date_value.strip() if isinstance(date_value, str) else "",
        "food_name": food_name_value.strip() if isinstance(food_name_value, str) else "",
        "calories": _as_int(form.get("calories")),
        "protein": _as_int(form.get("protein")),
        "carbs": _as_int(form.get("carbs")),
        "fats": _as_int(form.get("fats")),
    }

    token = request.session.get("access_token", "")
    if not token:
        return RedirectResponse("/login", status_code=303)

    status_code, data = create_food_log(token, payload)

    if status_code in (200, 201):
        return RedirectResponse("/home", status_code=303)

    message = data.get("detail") if isinstance(data, dict) else str(data)
    return JSONResponse({"ok": False, "message": message}, status_code=status_code)


@app.get("/home", include_in_schema=False)
def home_page(request: Request):
    user_email = request.session.get("user_email")
    if not user_email:
        return RedirectResponse("/login", status_code=303)

    logs = get_recent_logs_from_api(request)

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "request": request,
            "user_email": user_email,
            "logs": logs,
        },
    )


@app.get("/logout", include_in_schema=False)
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)