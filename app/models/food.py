import uuid
from datetime import datetime
from sqlalchemy import String, Float, Text, DateTime, Enum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.db.database import Base
import enum


class FoodStatus(str, enum.Enum):
    draft = "draft"
    verified = "verified"
    rejected = "rejected"


class Food(Base):
    __tablename__ = "foods"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Core identity
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    local_names: Mapped[list] = mapped_column(JSONB, default=list)   # ["ugali", "sima"]
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Region
    region: Mapped[str] = mapped_column(String(200), nullable=False)  # "Coast Kenya"
    region_normalized: Mapped[str] = mapped_column(String(200), nullable=False)  # "coast_kenya"
    
    # Price
    price_min_kes: Mapped[float] = mapped_column(Float, nullable=False)
    price_max_kes: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Meal info
    meal_type: Mapped[list] = mapped_column(JSONB, default=list)       # ["breakfast", "lunch"]
    ingredients: Mapped[list] = mapped_column(JSONB, default=list)
    common_at: Mapped[list] = mapped_column(JSONB, default=list)       # ["street stalls", "homes"]
    
    # Nutrition (rough)
    protein: Mapped[str] = mapped_column(String(10), nullable=True)   # "low", "medium", "high"
    carbs: Mapped[str] = mapped_column(String(10), nullable=True)
    vegetables: Mapped[str] = mapped_column(String(10), nullable=True)
    
    # Sub-regions within the country (e.g. counties for Kenya, districts for Uganda)
    sub_regions: Mapped[list] = mapped_column(JSONB, default=list)

    # Dietary tags
    tags: Mapped[list] = mapped_column(JSONB, default=list)            # ["halal", "vegetarian"]

    # Status
    status: Mapped[FoodStatus] = mapped_column(
        Enum(FoodStatus, schema='foods_knowledgebase'), default=FoodStatus.draft, nullable=False
    )

    # pgvector embedding (populated on approval)
    embedding: Mapped[list | None] = mapped_column(Vector(384), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
