from datetime import datetime
from pydantic import BaseModel, Field, model_validator


class GenerateFoodsRequest(BaseModel):
    region: str = Field(..., description="Region to generate foods for, e.g. 'Coast Kenya'")
    count: int = Field(default=5, ge=1, le=250, description="Number of foods to generate")


class FoodPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    local_names: list[str] = Field(default_factory=list)
    description: str = Field(..., min_length=1)
    price_min_kes: float = Field(..., ge=0)
    price_max_kes: float = Field(..., ge=0)
    meal_type: list[str] = Field(default_factory=list)
    ingredients: list[str] = Field(default_factory=list)
    common_at: list[str] = Field(default_factory=list)
    protein: str | None = None
    carbs: str | None = None
    vegetables: str | None = None
    sub_regions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_price_range(self):
        if self.price_max_kes < self.price_min_kes:
            raise ValueError("price_max_kes must be greater than or equal to price_min_kes")
        return self


class UploadFoodsRequest(BaseModel):
    region: str = Field(..., description="Region the uploaded foods belong to, e.g. 'Coast Kenya'")
    foods: list[FoodPayload] = Field(..., min_length=1, description="Foods to store as draft records")


class FoodOut(BaseModel):
    id: str
    name: str
    local_names: list[str] = []
    description: str
    region: str
    region_normalized: str
    price_min_kes: float
    price_max_kes: float
    meal_type: list[str] = []
    ingredients: list[str] = []
    common_at: list[str] = []
    protein: str | None = None
    carbs: str | None = None
    vegetables: str | None = None
    sub_regions: list[str] = []
    tags: list[str] = []
    status: str
    created_at: datetime
    approved_at: datetime | None = None

    model_config = {"from_attributes": True}


class GenerateResponse(BaseModel):
    region: str
    generated: int
    foods: list[FoodOut]


class ApproveResponse(BaseModel):
    message: str
    food: FoodOut


class BulkApproveResponse(BaseModel):
    message: str
    approved: int
    foods: list[FoodOut]


class RejectResponse(BaseModel):
    message: str
    food_id: str


class DraftsResponse(BaseModel):
    total: int
    region: str | None = None
    foods: list[FoodOut]


class RecommendRequest(BaseModel):
    region: str = Field(..., description="Region e.g. 'Coast Kenya'")
    budget_per_meal_kes: float = Field(..., gt=0, description="Max budget per meal in KES")
    dietary_goals: list[str] = Field(default=[], description="e.g. ['diabetic-friendly', 'high-protein']")
    exclude_food_ids: list[str] = Field(default=[], description="Food IDs to exclude (already served / rejected)")
    meal_type: str | None = Field(default=None, description="Filter to specific meal type: breakfast, lunch, dinner, snack")
    limit: int = Field(default=5, ge=1, le=20, description="Number of results to return")


class RecommendedFood(FoodOut):
    similarity: float = Field(..., description="Cosine similarity score (0-1)")


class RecommendResponse(BaseModel):
    region: str
    budget_per_meal_kes: float
    results: int
    foods: list[RecommendedFood]
