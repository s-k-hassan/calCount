import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 1. Get environment variables (with fallback defaults for local testing)
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./auth.db")

connect_args = {}
if DATABASE_TYPE == "sqlite":
    connect_args = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
