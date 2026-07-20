import os
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Any, Dict
from jose import jwt, JWTError
from passlib import context

import models, schemas
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

models.Base.metadata.create_all(bind=engine)

pwd_context = context.CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Environment Variables
SECRET_KEY: str = os.getenv("JWT_SECRET_KEY") or (
    "local_dev_secret_key_only" if os.getenv("ENV") == "development" else ""
)

if not SECRET_KEY:
    logger.log(level=50, msg="No secret key provided")
    raise RuntimeError("JWT_SECRET_KEY must be set in production!")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
logger.log(
    level=10,
    msg="ENV variables",
    extra={"algorithm": ALGORITHM, "access_token_expiry": ACCESS_TOKEN_EXPIRE_MINUTES},
)


# Functions for non-endpoint targets
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def create_access_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    to_encode = data.copy()
    effective_delta = expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + effective_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


auth = FastAPI(title="Calorie & Macro Tracker API", root_path="/auth")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = int(subject)
        if user_id is None:
            raise credentials_exception
        user_id_int = int(user_id)
    except (JWTError, ValueError):
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id_int).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


# Endpoints


@auth.post(
    "/register",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = (
        db.query(models.User).filter(models.User.email == payload.email).first()
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    db_user = models.User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        is_active=True,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@auth.post("/login")
def login_user(
    payload: schemas.UserCreate, db: Session = Depends(get_db)
) -> Dict[str, str]:
    db_user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not db_user or not verify_password(payload.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    if not db_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user account")
    access_token = create_access_token(data={"sub": str(db_user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@auth.put("/change-password", response_model=schemas.UserResponse)
def change_password(
    payload: schemas.UserPasswordChange,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect current password")

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    db.refresh(current_user)
    return current_user
