# import json
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from typing import Any

from helpers import (
    authenticate_with_auth_service,
    create_food_log,
    get_recent_logs_from_api,
)

## Begin Logging Engine
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
import logging, logging.config, yaml
from pathlib import Path

baseDir = Path(__file__).resolve().parent
config_path = baseDir / "logging_config.yaml"
otelEndpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "none")
if otelEndpoint != "none":
    logger_provider = LoggerProvider()
    set_logger_provider(logger_provider)
    exporter = OTLPLogExporter(endpoint=otelEndpoint, insecure=True)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
with open(config_path, "r") as configFile:
    config = yaml.safe_load(configFile.read())
    logging.config.dictConfig(config)
logger = logging.getLogger("loggerJSON")
## End Logging Engine

app = FastAPI(title="CalCount Web")
app.add_middleware(
    SessionMiddleware, secret_key="calcount-dev-secret", https_only=False
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8000")
API_SERVICE_URL = os.getenv("API_SERVICE_URL", "http://api-service:8000")
logger.log(
    level=20,
    msg="ENV variables",
    extra={"AUTH_SERVICE_URL": AUTH_SERVICE_URL, "API_SERVICE_URL": API_SERVICE_URL},
)


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
        logger.info(msg="User Login", extra={"email": email})
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
    logger.info(msg="User Created", extra={"email": email})
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
        "food_name": (
            food_name_value.strip() if isinstance(food_name_value, str) else ""
        ),
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
        logger.info(
            msg="Food Logged",
            extra={
                "email": request.session.get("user_email"),
                "entry_date": payload["date"],
                "details": payload["food_name"],
                "nutrition": {
                    "calories": payload["calories"],
                    "protein": payload["protein"],
                    "fats": payload["fats"],
                    "carbs": payload["carbs"],
                },
            },
        )
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


@app.get("/dashboard", include_in_schema=False)
def dashboard_page(request: Request):
    user_email = request.session.get("user_email")
    if not user_email:
        return RedirectResponse("/login", status_code=303)

    logs = get_recent_logs_from_api(request)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
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
