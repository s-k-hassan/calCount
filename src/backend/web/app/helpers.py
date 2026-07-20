import json
import os
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen
from fastapi import Request
from typing import Any

import logging, logging.config
from pythonjsonlogger.json import JsonFormatter

## Begin Logging Engine
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from pythonjsonlogger.json import JsonFormatter
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


def _call_api(
    method: str,
    path: str,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
):
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
    status_code, data = _call_api("POST", "/logs", token=token, payload=payload)
    logging.info(
        "create_food_log status=%s payload=%s response=%s", status_code, payload, data
    )
    return status_code, data


def fetch_logs_for_date(token: str, day: str):
    query = urlencode({"date": day})
    status_code, data = _call_api("GET", f"/logs?{query}", token=token)
    logging.info(
        "fetch_logs_for_date day=%s status=%s response=%s", day, status_code, data
    )
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
