import os
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from typing import List
import models as models, schemas as schemas
from database import SessionLocal, engine

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

# --- SECURITY SCHEME ---
SERVICE_URL = os.getenv("SERVICE_URL", "localhost:8001")
ALGORITHM = "HS256"

SECRET_KEY: str = os.getenv("JWT_SECRET_KEY") or (
    "local_dev_secret_key_only" if os.getenv("ENV") == "development" else ""
)
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY must be set in production!")


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{SERVICE_URL}/login")

models.Base.metadata.create_all(bind=engine)
app = FastAPI(title="Calorie & Macro Tracker API", root_path="/v1")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")

        if not isinstance(subject, str):
            raise credentials_exception

        return int(subject)
    except (JWTError, ValueError):
        raise credentials_exception


# --- ENDPOINTS ---
@app.post("/logs", response_model=schemas.FoodLogResponse)
def create_food_log(
    payload: schemas.FoodLogCreate,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    db_log = models.FoodLog(**payload.model_dump(), user_id=current_user_id)
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log


@app.get("/logs", response_model=List[schemas.FoodLogResponse])
def get_food_logs(
    date: str = Query(..., description="Format: YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    logs = (
        db.query(models.FoodLog)
        .filter(models.FoodLog.user_id == current_user_id, models.FoodLog.date == date)
        .all()
    )
    return logs


@app.put("/logs/{log_id}", response_model=schemas.FoodLogResponse)
def update_food_log(
    log_id: int,
    payload: schemas.FoodLogCreate,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    # Ensure the log exists AND belongs to the requesting user
    db_log = (
        db.query(models.FoodLog)
        .filter(models.FoodLog.id == log_id, models.FoodLog.user_id == current_user_id)
        .first()
    )

    if not db_log:
        raise HTTPException(
            status_code=404, detail="Food log not found or unauthorized"
        )

    update_data = payload.model_dump()
    for key, value in update_data.items():
        setattr(db_log, key, value)

    db.commit()
    db.refresh(db_log)
    return db_log


@app.delete("/logs/{log_id}")
def delete_food_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    # Ensure the log exists AND belongs to the requesting user
    db_log = (
        db.query(models.FoodLog)
        .filter(models.FoodLog.id == log_id, models.FoodLog.user_id == current_user_id)
        .first()
    )

    if not db_log:
        raise HTTPException(
            status_code=404, detail=f"Food log with ID {log_id} not found"
        )
    db.delete(db_log)
    db.commit()
    return {"message": f"Food log entry {log_id} was successfully deleted"}


@app.get("/summary")
def get_daily_summary(
    date: str = Query(..., description="Format: YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    # Base summary completely on isolated user data
    logs = (
        db.query(models.FoodLog)
        .filter(models.FoodLog.user_id == current_user_id, models.FoodLog.date == date)
        .all()
    )

    return {
        "date": date,
        "total_calories": sum(item.calories for item in logs),
        "total_protein_grams": sum(item.protein for item in logs),
        "total_carbs_grams": sum(item.carbs for item in logs),
        "total_fats_grams": sum(item.fats for item in logs),
        "items_logged": len(logs),
    }
