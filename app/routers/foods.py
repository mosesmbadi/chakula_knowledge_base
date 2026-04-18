import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, or_, and_, literal
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import get_db
from app.models.food import Food, FoodStatus
from app.models.schemas import (
    GenerateFoodsRequest,
    GenerateResponse,
    ApproveResponse,
    BulkApproveResponse,
    RejectResponse,
    DraftsResponse,
    FoodOut,
    FoodPayload,
    RecommendRequest,
    RecommendResponse,
    RecommendedFood,
    UploadFoodsRequest,
)
from app.services.llm_service import GeminiServiceUnavailableError, generate_foods_from_llm
from app.services.embedding_service import embed_food, embed_query
from app.auth import require_api_key

router = APIRouter(prefix="/foods", tags=["foods"], dependencies=[Depends(require_api_key)])
generation_router = APIRouter(prefix="/api/foods", tags=["foods"], dependencies=[Depends(require_api_key)])


def normalize_region(region: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", region.lower()).strip("_")


async def _save_food_entries(region: str, entries: list[dict] | list[FoodPayload], db: AsyncSession) -> GenerateResponse:
    region_normalized = normalize_region(region)
    existing_result = await db.execute(
        select(func.lower(Food.name)).where(Food.region_normalized == region_normalized)
    )
    existing_names: set[str] = {row[0] for row in existing_result.all()}

    saved: list[Food] = []

    for entry in entries:
        entry_data = entry.model_dump() if isinstance(entry, FoodPayload) else entry

        try:
            name = entry_data["name"].strip()
            if not name:
                continue
            if name.lower() in existing_names:
                continue

            food = Food(
                name=name,
                local_names=entry_data.get("local_names", []),
                description=entry_data["description"],
                region=region,
                region_normalized=region_normalized,
                price_min_kes=float(entry_data["price_min_kes"]),
                price_max_kes=float(entry_data["price_max_kes"]),
                meal_type=entry_data.get("meal_type", []),
                ingredients=entry_data.get("ingredients", []),
                common_at=entry_data.get("common_at", []),
                protein=entry_data.get("protein"),
                carbs=entry_data.get("carbs"),
                vegetables=entry_data.get("vegetables"),
                sub_regions=entry_data.get("sub_regions", []),
                tags=entry_data.get("tags", []),
                status=FoodStatus.draft,
            )
            db.add(food)
            saved.append(food)
            existing_names.add(name.lower())
        except (KeyError, ValueError, TypeError):
            continue

    await db.commit()
    for food in saved:
        await db.refresh(food)

    return GenerateResponse(
        region=region,
        generated=len(saved),
        foods=[FoodOut.model_validate(food) for food in saved],
    )


# ---------------------------------------------------------------------------
# POST /foods/generate
# ---------------------------------------------------------------------------
@router.post("/generate", response_model=GenerateResponse, status_code=201)
@generation_router.post("/generate", response_model=GenerateResponse, status_code=201)
async def generate_foods(payload: GenerateFoodsRequest, db: AsyncSession = Depends(get_db)):
    """
    Generate food entries for a given region with Gemini, or store manually uploaded foods.
    All entries are saved as DRAFT so they need human approval before going live.
    """
    if payload.foods is not None:
        return await _save_food_entries(payload.region, payload.foods, db)

    try:
        raw_foods = await generate_foods_from_llm(payload.region, payload.count or 0)
    except GeminiServiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return await _save_food_entries(payload.region, raw_foods, db)


@router.post("/generate/upload/", response_model=GenerateResponse, status_code=201)
@generation_router.post("/generate/upload/", response_model=GenerateResponse, status_code=201)
async def upload_foods(payload: UploadFoodsRequest, db: AsyncSession = Depends(get_db)):
    """
    Store manually provided foods for a region.
    Uploaded entries are saved as DRAFT so they follow the same approval flow as LLM-generated foods.
    """
    return await _save_food_entries(payload.region, payload.foods, db)


# ---------------------------------------------------------------------------
# GET /foods/drafts
# ---------------------------------------------------------------------------
@router.get("/drafts", response_model=DraftsResponse)
async def list_drafts(
    region: str | None = Query(default=None, description="Filter by region e.g. 'Coast Kenya'"),
    db: AsyncSession = Depends(get_db),
):
    """
    List all food entries with status=draft, optionally filtered by region.
    This is the queue a human reviewer works through.
    """
    stmt = select(Food).where(Food.status == FoodStatus.draft)

    if region:
        normalized = normalize_region(region)
        stmt = stmt.where(Food.region_normalized == normalized)

    stmt = stmt.order_by(Food.created_at.desc())
    result = await db.execute(stmt)
    foods = result.scalars().all()

    return DraftsResponse(
        total=len(foods),
        region=region,
        foods=[FoodOut.model_validate(f) for f in foods],
    )


# ---------------------------------------------------------------------------
# POST /foods/{id}/approve
# ---------------------------------------------------------------------------
@router.post("/{food_id}/approve", response_model=ApproveResponse)
async def approve_food(food_id: str, db: AsyncSession = Depends(get_db)):
    """
    Approve a draft food entry.
    This:
    1. Generates a pgvector embedding from the food's text
    2. Sets status to 'verified'
    3. Records the approval timestamp
    After this, the food is live and queryable via semantic search.
    """
    food = await db.get(Food, food_id)

    if not food:
        raise HTTPException(status_code=404, detail="Food not found")
    if food.status == FoodStatus.verified:
        raise HTTPException(status_code=400, detail="Food is already verified")
    if food.status == FoodStatus.rejected:
        raise HTTPException(status_code=400, detail="Cannot approve a rejected entry")

    # Generate and store the embedding
    food.embedding = embed_food(food)
    food.status = FoodStatus.verified
    food.approved_at = datetime.utcnow()

    await db.commit()
    await db.refresh(food)

    return ApproveResponse(
        message=f"'{food.name}' approved and embedded successfully.",
        food=FoodOut.model_validate(food),
    )


# ---------------------------------------------------------------------------
# POST /foods/approve-all
# ---------------------------------------------------------------------------
@router.post("/approve-all", response_model=BulkApproveResponse)
async def approve_all_drafts(
    region: str | None = Query(default=None, description="Optional region filter"),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve all draft food entries at once, and embed any verified foods that
    are missing embeddings (e.g. seeded directly into the DB).
    Optionally filter by region.
    """
    stmt = select(Food).where(
        or_(
            Food.status == FoodStatus.draft,
            and_(Food.status == FoodStatus.verified, Food.embedding.is_(None)),
        )
    )
    if region:
        stmt = stmt.where(Food.region_normalized == normalize_region(region))

    result = await db.execute(stmt)
    pending = result.scalars().all()

    if not pending:
        raise HTTPException(status_code=404, detail="No foods to approve or embed")

    now = datetime.utcnow()
    for food in pending:
        food.embedding = embed_food(food)
        if food.status == FoodStatus.draft:
            food.status = FoodStatus.verified
            food.approved_at = now

    await db.commit()
    for food in pending:
        await db.refresh(food)

    return BulkApproveResponse(
        message=f"Approved/embedded {len(pending)} foods.",
        approved=len(pending),
        foods=[FoodOut.model_validate(f) for f in pending],
    )


# ---------------------------------------------------------------------------
# POST /foods/{id}/reject
# ---------------------------------------------------------------------------
@router.post("/{food_id}/reject", response_model=RejectResponse)
async def reject_food(food_id: str, db: AsyncSession = Depends(get_db)):
    """
    Reject a draft food entry — marks it as rejected so it won't appear in drafts queue.
    We keep the record for audit purposes rather than hard-deleting.
    """
    food = await db.get(Food, food_id)

    if not food:
        raise HTTPException(status_code=404, detail="Food not found")
    if food.status != FoodStatus.draft:
        raise HTTPException(status_code=400, detail=f"Only drafts can be rejected. Current status: {food.status}")

    food.status = FoodStatus.rejected
    await db.commit()

    return RejectResponse(
        message=f"'{food.name}' rejected and removed from review queue.",
        food_id=food_id,
    )


# ---------------------------------------------------------------------------
# POST /foods/recommend
# ---------------------------------------------------------------------------
@router.post("/recommend", response_model=RecommendResponse)
async def recommend_foods(payload: RecommendRequest, db: AsyncSession = Depends(get_db)):
    """
    Semantic food recommendation.
    Finds the best matching verified meals based on region, budget,
    dietary goals, and exclusion list using pgvector cosine similarity.
    """
    # Build a natural-language query for embedding
    query_parts = [f"food from {payload.region}"]
    if payload.meal_type:
        query_parts.append(f"{payload.meal_type} meal")
    if payload.dietary_goals:
        query_parts.append(", ".join(payload.dietary_goals))
    query_text = ". ".join(query_parts)

    query_vector = embed_query(query_text)

    # Cosine distance (pgvector <=> operator) — lower = more similar
    query_vector_cast = cast(query_vector, Vector(384))
    similarity_expr = (1 - Food.embedding.cosine_distance(query_vector_cast)).label("similarity")

    stmt = (
        select(Food, similarity_expr)
        .where(Food.status == FoodStatus.verified)
        .where(Food.embedding.isnot(None))
        .where(Food.price_max_kes <= payload.budget_per_meal_kes)
    )

    # Region filter
    normalized = normalize_region(payload.region)
    stmt = stmt.where(Food.region_normalized == normalized)

    # Meal type filter
    if payload.meal_type:
        stmt = stmt.where(Food.meal_type.op("@>")(cast([payload.meal_type], JSONB)))

    # Exclude specific food IDs (already served / user rejected)
    if payload.exclude_food_ids:
        stmt = stmt.where(Food.id.notin_(payload.exclude_food_ids))

    # Dietary goal filtering
    # Known goals map to nutritional attributes; unknown goals match tags exactly
    DIETARY_NUTRITION_MAP = {
        "gain_weight": or_(Food.carbs == "high", Food.protein == "high"),
        "lose_weight": or_(Food.carbs == "low", Food.vegetables == "high"),
        "high-protein": Food.protein == "high",
        "low-carb": Food.carbs == "low",
        "high-fibre": Food.vegetables == "high",
    }
    for goal in payload.dietary_goals:
        if goal in DIETARY_NUTRITION_MAP:
            stmt = stmt.where(DIETARY_NUTRITION_MAP[goal])
        else:
            stmt = stmt.where(Food.tags.op("@>")(cast([goal], JSONB)))

    # Order by similarity (highest first) and limit
    stmt = stmt.order_by(similarity_expr.desc()).limit(payload.limit)

    result = await db.execute(stmt)
    rows = result.all()

    foods = [
        RecommendedFood(
            **FoodOut.model_validate(food).model_dump(),
            similarity=round(float(sim), 4),
        )
        for food, sim in rows
    ]

    return RecommendResponse(
        region=payload.region,
        budget_per_meal_kes=payload.budget_per_meal_kes,
        results=len(foods),
        foods=foods,
    )


# ---------------------------------------------------------------------------
# GET /foods/verified  (bonus — list what's live)
# ---------------------------------------------------------------------------
@router.get("/verified", response_model=DraftsResponse)
async def list_verified(
    region: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """List all verified (live) food entries, optionally filtered by region."""
    stmt = select(Food).where(Food.status == FoodStatus.verified)

    if region:
        normalized = normalize_region(region)
        stmt = stmt.where(Food.region_normalized == normalized)

    stmt = stmt.order_by(Food.approved_at.desc())
    result = await db.execute(stmt)
    foods = result.scalars().all()

    return DraftsResponse(
        total=len(foods),
        region=region,
        foods=[FoodOut.model_validate(f) for f in foods],
    )
