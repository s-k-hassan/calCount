import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 1. Get environment variables (with fallback defaults for local testing)
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite")

connect_args = {}
match DATABASE_TYPE:
    case "sqlite":
        DATABASE_URL = "sqlite:///./tracker.db"
        connect_args = {"check_same_thread": False}
    case "postgres":
        POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
        POSTGRES_USER = os.getenv("POSTGRES_USER")
        POSTGRES_DB_NAME = os.getenv("POSTGRES_DB_NAME")
        DATABASE_URL = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@api-database/{POSTGRES_DB_NAME}"
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
