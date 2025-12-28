"""
SQLAlchemy ORM models for insurance pricing.
No raw SQL - pure ORM as requested.
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class PricingDataset(Base):
    """Tracks which Excel uploads are active."""
    __tablename__ = "pricing_datasets"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    row_count = Column(Integer, default=0)

    prices = relationship("InsurancePrice", back_populates="dataset")


class InsurancePrice(Base):
    """
    Core pricing table - one row per unique combination.
    Indexed for fast real-time lookups.
    """
    __tablename__ = "insurance_prices"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("pricing_datasets.id"), nullable=False)

    # Lookup keys (what the UI sends)
    age_min = Column(Integer, nullable=False)
    age_max = Column(Integer, nullable=False)
    zip_prefix = Column(String(3), nullable=False)  # First 3 digits of ZIP
    insurance_model = Column(String, nullable=False)  # e.g., "basic", "standard", "premium"
    deductible = Column(Integer, nullable=False)  # e.g., 300, 500, 1000, 2500
    accident_coverage = Column(Boolean, default=False)

    # Pricing output
    monthly_premium = Column(Float, nullable=False)
    annual_premium = Column(Float, nullable=False)
    provider_name = Column(String, nullable=False)
    provider_code = Column(String, nullable=False)

    dataset = relationship("PricingDataset", back_populates="prices")

    # Indexes for fast queries
    __table_args__ = (
        Index('idx_pricing_lookup', 'dataset_id', 'zip_prefix', 'insurance_model', 'deductible'),
        Index('idx_age_range', 'age_min', 'age_max'),
    )


class Provider(Base):
    """Insurance providers for comparison."""
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    logo_url = Column(String)
    is_active = Column(Boolean, default=True)
