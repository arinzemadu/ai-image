import os
from dotenv import load_dotenv
load_dotenv() # Load variables from .env if it exists

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# If a DATABASE_URL is set (in production on Render), use it. 
# Otherwise, fall back to a local SQLite database file.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./database.db")

# The 'connect_args' are only for SQLite. They are not needed for PostgreSQL.
engine_args = {}
if DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
