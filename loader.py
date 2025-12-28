"""
Excel-to-Database loader for pricing data.
Reads Excel files and populates the pricing tables.
"""
import pandas as pd
from sqlalchemy.orm import Session
from database import SessionLocal, init_db
from models import PricingDataset, InsurancePrice, Provider
from datetime import datetime


def load_excel_pricing(file_path: str, dataset_name: str = None) -> int:
    """
    Load pricing data from Excel file into database.

    Expected Excel columns:
    - age_min, age_max (or just 'age' for single value)
    - zip_prefix (3 digits) or zip_code (5 digits, we'll extract prefix)
    - insurance_model (basic/standard/premium)
    - deductible (300/500/1000/2500)
    - accident_coverage (yes/no or true/false)
    - monthly_premium
    - annual_premium (optional - calculated from monthly if missing)
    - provider_name
    - provider_code

    Returns: number of rows loaded
    """
    db = SessionLocal()

    try:
        # Read Excel
        df = pd.read_excel(file_path)
        print(f"Read {len(df)} rows from {file_path}")

        # Normalize column names
        df.columns = df.columns.str.lower().str.strip().str.replace(' ', '_')

        # Handle age columns
        if 'age' in df.columns and 'age_min' not in df.columns:
            df['age_min'] = df['age']
            df['age_max'] = df['age']

        # Handle ZIP
        if 'zip_code' in df.columns and 'zip_prefix' not in df.columns:
            df['zip_prefix'] = df['zip_code'].astype(str).str[:3]

        # Handle annual premium
        if 'annual_premium' not in df.columns:
            df['annual_premium'] = df['monthly_premium'] * 12

        # Handle accident coverage
        if 'accident_coverage' in df.columns:
            df['accident_coverage'] = df['accident_coverage'].apply(
                lambda x: str(x).lower() in ('yes', 'true', '1', 'y')
            )
        else:
            df['accident_coverage'] = False

        # Deactivate old datasets
        db.query(PricingDataset).update({PricingDataset.is_active: False})

        # Create new dataset
        dataset = PricingDataset(
            name=dataset_name or f"Import {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            is_active=True,
            row_count=len(df),
        )
        db.add(dataset)
        db.flush()  # Get the ID

        # Insert prices
        for _, row in df.iterrows():
            price = InsurancePrice(
                dataset_id=dataset.id,
                age_min=int(row['age_min']),
                age_max=int(row['age_max']),
                zip_prefix=str(row['zip_prefix']),
                insurance_model=str(row['insurance_model']).lower(),
                deductible=int(row['deductible']),
                accident_coverage=bool(row['accident_coverage']),
                monthly_premium=float(row['monthly_premium']),
                annual_premium=float(row['annual_premium']),
                provider_name=str(row['provider_name']),
                provider_code=str(row['provider_code']),
            )
            db.add(price)

        db.commit()
        print(f"Loaded {len(df)} prices into dataset '{dataset.name}'")
        return len(df)

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def generate_sample_data() -> int:
    """
    Generate sample pricing data for demo purposes.
    Creates realistic Swiss health insurance pricing.
    """
    db = SessionLocal()
    init_db()

    try:
        # Deactivate old
        db.query(PricingDataset).update({PricingDataset.is_active: False})

        # Create sample dataset
        dataset = PricingDataset(
            name="Demo Pricing Data",
            is_active=True,
            row_count=0,
        )
        db.add(dataset)
        db.flush()

        # Sample providers (Swiss insurers)
        providers = [
            ("Helsana", "HEL"),
            ("CSS", "CSS"),
            ("Swica", "SWI"),
            ("Sanitas", "SAN"),
            ("Concordia", "CON"),
        ]

        # Age brackets
        age_brackets = [
            (18, 25),
            (26, 35),
            (36, 45),
            (46, 55),
            (56, 65),
            (66, 100),
        ]

        # ZIP prefixes (Swiss cantons)
        zip_prefixes = ["800", "801", "802", "803", "810", "820", "830", "840", "850", "860"]

        # Insurance models
        models = ["basic", "standard", "premium"]

        # Deductibles (Swiss standard)
        deductibles = [300, 500, 1000, 1500, 2000, 2500]

        count = 0
        for provider_name, provider_code in providers:
            # Base rate varies by provider
            provider_base = {"HEL": 1.0, "CSS": 0.95, "SWI": 1.05, "SAN": 0.98, "CON": 0.92}[provider_code]

            for age_min, age_max in age_brackets:
                # Age affects price
                age_factor = 1.0 + (age_min - 25) * 0.015

                for zip_prefix in zip_prefixes:
                    # Region affects price
                    region_factor = 0.9 + (int(zip_prefix[1]) * 0.02)

                    for model in models:
                        # Model affects price
                        model_factor = {"basic": 1.0, "standard": 1.15, "premium": 1.35}[model]

                        for deductible in deductibles:
                            # Higher deductible = lower premium
                            deductible_factor = 1.0 - (deductible - 300) * 0.0002

                            for accident in [False, True]:
                                # Accident coverage adds ~10%
                                accident_factor = 1.10 if accident else 1.0

                                # Calculate premium
                                base_monthly = 280  # CHF base
                                monthly = (
                                    base_monthly
                                    * provider_base
                                    * age_factor
                                    * region_factor
                                    * model_factor
                                    * deductible_factor
                                    * accident_factor
                                )

                                price = InsurancePrice(
                                    dataset_id=dataset.id,
                                    age_min=age_min,
                                    age_max=age_max,
                                    zip_prefix=zip_prefix,
                                    insurance_model=model,
                                    deductible=deductible,
                                    accident_coverage=accident,
                                    monthly_premium=round(monthly, 2),
                                    annual_premium=round(monthly * 12, 2),
                                    provider_name=provider_name,
                                    provider_code=provider_code,
                                )
                                db.add(price)
                                count += 1

        dataset.row_count = count
        db.commit()
        print(f"Generated {count} sample price rows")
        return count

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Load from Excel
        load_excel_pricing(sys.argv[1])
    else:
        # Generate sample data
        generate_sample_data()
