from sentence_transformers import SentenceTransformer
from app.config import settings
from app.models.food import Food

# Load once at startup — model is cached after first load
_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _model


def build_food_text(food: Food) -> str:
    """
    Construct a rich text string from a food record for embedding.
    This is what gets semantically searchable — the richer the text, the better the retrieval.
    """
    local = ", ".join(food.local_names) if food.local_names else ""
    ingredients = ", ".join(food.ingredients) if food.ingredients else ""
    common_at = ", ".join(food.common_at) if food.common_at else ""
    meal_type = ", ".join(food.meal_type) if food.meal_type else ""
    tags = ", ".join(food.tags) if food.tags else ""

    parts = [
        f"{food.name}",
        f"Local names: {local}" if local else "",
        f"Region: {food.region}",
        f"Description: {food.description}",
        f"Ingredients: {ingredients}" if ingredients else "",
        f"Meal type: {meal_type}" if meal_type else "",
        f"Common at: {common_at}" if common_at else "",
        f"Price: KES {food.price_min_kes}–{food.price_max_kes}",
        f"Nutrition — Protein: {food.protein}, Carbs: {food.carbs}, Vegetables: {food.vegetables}",
        f"Tags: {tags}" if tags else "",
    ]

    return ". ".join(p for p in parts if p)


def embed_food(food: Food) -> list[float]:
    """Generate a 384-dim embedding vector for a food record."""
    model = get_embedding_model()
    text = build_food_text(food)
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_query(query: str) -> list[float]:
    """Generate a 384-dim embedding vector for a search query."""
    model = get_embedding_model()
    vector = model.encode(query, normalize_embeddings=True)
    return vector.tolist()
