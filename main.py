"""
Lamalux Pricing API
Real-time insurance premium quotes from Excel-driven database.

Endpoints:
- POST /api/prices/quote - Get quote for single configuration
- POST /api/prices/compare - Compare quotes across providers
"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from database import get_db, init_db
from models import InsurancePrice, PricingDataset, Provider

app = FastAPI(
    title="Lamalux Pricing API",
    description="Real-time insurance premium quotes",
    version="1.0.0",
)

# CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Request/Response Models ===

class QuoteRequest(BaseModel):
    age: int = Field(..., ge=18, le=100, description="Customer age")
    zip_code: str = Field(..., min_length=5, max_length=5, description="5-digit ZIP code")
    insurance_model: str = Field(..., description="basic, standard, or premium")
    deductible: int = Field(..., description="Deductible amount (300, 500, 1000, 2500)")
    accident_coverage: bool = Field(default=False, description="Include accident coverage")


class QuoteResponse(BaseModel):
    provider_name: str
    provider_code: str
    monthly_premium: float
    annual_premium: float
    deductible: int
    insurance_model: str
    accident_coverage: bool


class CompareRequest(BaseModel):
    age: int = Field(..., ge=18, le=100)
    zip_code: str = Field(..., min_length=5, max_length=5)
    insurance_model: Optional[str] = None  # If None, compare all models
    deductible: Optional[int] = None  # If None, compare all deductibles
    accident_coverage: bool = False


class CompareResponse(BaseModel):
    quotes: List[QuoteResponse]
    cheapest: Optional[QuoteResponse]
    query_time_ms: float


# === API Endpoints ===

@app.post("/api/prices/quote", response_model=List[QuoteResponse])
def get_quote(request: QuoteRequest, db: Session = Depends(get_db)):
    """
    Get insurance quotes for a specific configuration.
    Returns all matching providers.
    """
    zip_prefix = request.zip_code[:3]

    # Query active dataset
    active_dataset = db.query(PricingDataset).filter(
        PricingDataset.is_active == True
    ).first()

    if not active_dataset:
        raise HTTPException(status_code=404, detail="No active pricing dataset")

    # Find matching prices (ORM query, no raw SQL)
    prices = db.query(InsurancePrice).filter(
        and_(
            InsurancePrice.dataset_id == active_dataset.id,
            InsurancePrice.zip_prefix == zip_prefix,
            InsurancePrice.insurance_model == request.insurance_model,
            InsurancePrice.deductible == request.deductible,
            InsurancePrice.accident_coverage == request.accident_coverage,
            InsurancePrice.age_min <= request.age,
            InsurancePrice.age_max >= request.age,
        )
    ).all()

    if not prices:
        raise HTTPException(
            status_code=404,
            detail=f"No quotes found for ZIP {zip_prefix}*, age {request.age}, {request.insurance_model}"
        )

    return [
        QuoteResponse(
            provider_name=p.provider_name,
            provider_code=p.provider_code,
            monthly_premium=round(p.monthly_premium, 2),
            annual_premium=round(p.annual_premium, 2),
            deductible=p.deductible,
            insurance_model=p.insurance_model,
            accident_coverage=p.accident_coverage,
        )
        for p in prices
    ]


@app.post("/api/prices/compare", response_model=CompareResponse)
def compare_quotes(request: CompareRequest, db: Session = Depends(get_db)):
    """
    Compare quotes across providers and configurations.
    Returns all matching quotes sorted by price, plus the cheapest option.
    """
    import time
    start = time.time()

    zip_prefix = request.zip_code[:3]

    active_dataset = db.query(PricingDataset).filter(
        PricingDataset.is_active == True
    ).first()

    if not active_dataset:
        raise HTTPException(status_code=404, detail="No active pricing dataset")

    # Build query filters
    filters = [
        InsurancePrice.dataset_id == active_dataset.id,
        InsurancePrice.zip_prefix == zip_prefix,
        InsurancePrice.accident_coverage == request.accident_coverage,
        InsurancePrice.age_min <= request.age,
        InsurancePrice.age_max >= request.age,
    ]

    if request.insurance_model:
        filters.append(InsurancePrice.insurance_model == request.insurance_model)

    if request.deductible:
        filters.append(InsurancePrice.deductible == request.deductible)

    # Query and sort by price
    prices = db.query(InsurancePrice).filter(
        and_(*filters)
    ).order_by(InsurancePrice.monthly_premium).all()

    quotes = [
        QuoteResponse(
            provider_name=p.provider_name,
            provider_code=p.provider_code,
            monthly_premium=round(p.monthly_premium, 2),
            annual_premium=round(p.annual_premium, 2),
            deductible=p.deductible,
            insurance_model=p.insurance_model,
            accident_coverage=p.accident_coverage,
        )
        for p in prices
    ]

    elapsed_ms = (time.time() - start) * 1000

    return CompareResponse(
        quotes=quotes,
        cheapest=quotes[0] if quotes else None,
        query_time_ms=round(elapsed_ms, 2),
    )


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """Health check - verify DB connection and active dataset."""
    active = db.query(PricingDataset).filter(PricingDataset.is_active == True).first()
    return {
        "status": "healthy",
        "active_dataset": active.name if active else None,
        "row_count": active.row_count if active else 0,
    }


@app.get("/api/options")
def get_options(db: Session = Depends(get_db)):
    """Return available options for the UI dropdowns."""
    active = db.query(PricingDataset).filter(PricingDataset.is_active == True).first()
    if not active:
        return {"insurance_models": [], "deductibles": [], "providers": []}

    # Get distinct values from active dataset
    models = db.query(InsurancePrice.insurance_model).filter(
        InsurancePrice.dataset_id == active.id
    ).distinct().all()

    deductibles = db.query(InsurancePrice.deductible).filter(
        InsurancePrice.dataset_id == active.id
    ).distinct().order_by(InsurancePrice.deductible).all()

    providers = db.query(InsurancePrice.provider_name, InsurancePrice.provider_code).filter(
        InsurancePrice.dataset_id == active.id
    ).distinct().all()

    return {
        "insurance_models": [m[0] for m in models],
        "deductibles": [d[0] for d in deductibles],
        "providers": [{"name": p[0], "code": p[1]} for p in providers],
    }


# Initialize DB on startup
@app.on_event("startup")
def startup():
    init_db()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
