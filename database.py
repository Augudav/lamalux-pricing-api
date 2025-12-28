"""
Database setup - SQLAlchemy with PostgreSQL (SQLite for demo).
Easily swappable to Postgres by changing DATABASE_URL.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

# For demo: SQLite. For production: PostgreSQL
# DATABASE_URL = "postgresql://user:pass@localhost/lamalux_pricing"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pricing.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,  # Set True for SQL debugging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for FastAPI - yields DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
