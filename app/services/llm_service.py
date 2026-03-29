import json
import re
from google import genai
from google.genai import types
from app.config import settings

import logging

logger = logging.getLogger(__name__)


GENERATION_PROMPT = """You are a food culture expert specializing in African and Middle Eastern cuisine.

Generate {count} traditional/common foods eaten in the region: "{region}"

For each food, return a JSON array where each item has EXACTLY these fields:
- name: string (common English name)
- local_names: array of strings (local language names, can be empty)
- description: string (1-2 sentences, what it is and how it's eaten)
- price_min_kes: number (minimum typical street/market price in Kenyan Shillings — convert from local currency if not Kenya)
- price_max_kes: number (maximum typical price in KES)
- meal_type: array of strings — any of ["breakfast", "lunch", "dinner", "snack"]
- ingredients: array of strings (main ingredients, max 6)
- common_at: array of strings (where it's sold/eaten e.g. "street stalls", "homes", "restaurants")
- protein: string — one of "low", "medium", "high"
- carbs: string — one of "low", "medium", "high"
- vegetables: string — one of "low", "medium", "high"
- sub_regions: array of strings — the specific sub-regions within the country where this food is most common (e.g. counties for Kenya like ["Mombasa", "Kilifi", "Kwale"], districts for Uganda like ["Kampala", "Wakiso"], states/provinces for other countries where applicable). Leave empty if the food is equally common across the whole region.
- tags: array of strings — any applicable: ["vegetarian", "vegan", "halal", "gluten-free", "dairy-free", "diabetic-friendly", "low-sugar", "low-glycemic", "high-calorie", "high-protein", "low-calorie", "low-fat", "heart-healthy", "kidney-friendly"]

Important rules:
- Prices must be realistic and specific to the region and its economic context
- Include a mix of meal types and price ranges
- Focus on foods actually eaten by ordinary people, not just restaurants
- Be culturally accurate: e.g. for Kenya, breakfast foods include mandazi, chai, uji, mkate, maandazi — NOT ugali or matooke which are lunch/dinner staples
- Return ONLY a valid JSON array, no explanation or markdown fences

Region: {region}
Count: {count}"""


BATCH_SIZE = 10  # max foods per LLM call — keeps responses fast and parseable
MAX_RETRIES = 3  # retry on bad JSON from the LLM


def _get_client() -> genai.Client:
    return genai.Client(api_key=settings.GEMINI_API_KEY)


async def _generate_batch(client: genai.Client, region: str, count: int) -> list[dict]:
    """Single Gemini call for up to BATCH_SIZE foods. Retries on parse failure."""
    prompt = GENERATION_PROMPT.format(region=region, count=count)
    config = types.GenerateContentConfig(
        temperature=0.4,
        top_p=0.9,
        response_mime_type="application/json",
    )

    for attempt in range(1, MAX_RETRIES + 1):
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        raw = response.text

        try:
            return _parse_llm_response(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "LLM JSON parse failed (attempt %d/%d): %s\nRaw (first 500 chars): %s",
                attempt, MAX_RETRIES, exc, raw[:500],
            )
            if attempt == MAX_RETRIES:
                raise


async def generate_foods_from_llm(region: str, count: int) -> list[dict]:
    """
    Call the Gemini API and parse the structured food list it returns.
    Large counts are split into batches.
    """
    client = _get_client()
    all_foods: list[dict] = []

    remaining = count
    while remaining > 0:
        batch = min(remaining, BATCH_SIZE)
        foods = await _generate_batch(client, region, batch)
        all_foods.extend(foods)
        remaining -= batch

    return all_foods


def _parse_llm_response(raw: str) -> list[dict]:
    """
    Extract and parse the JSON array from the LLM response.
    LLMs sometimes wrap JSON in markdown fences or produce slightly invalid JSON.
    """
    # Strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```").strip()

    # Find the JSON array (starts with [ ends with ])
    start = cleaned.find("[")
    end = cleaned.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON array found in LLM response. Raw: {raw[:300]}")

    json_str = cleaned[start:end]

    # Try parsing as-is first
    try:
        foods = json.loads(json_str)
    except json.JSONDecodeError:
        # Common LLM issues: trailing commas, truncated output
        # Remove trailing commas before ] or }
        fixed = re.sub(r",\s*([}\]])", r"\1", json_str)
        try:
            foods = json.loads(fixed)
        except json.JSONDecodeError:
            # JSON may be truncated — try to salvage complete objects
            foods = _salvage_partial_json(json_str)

    if not isinstance(foods, list):
        raise ValueError("LLM response did not return a JSON array")

    return foods


def _salvage_partial_json(json_str: str) -> list[dict]:
    """
    Attempt to recover valid items from a truncated JSON array.
    Finds the last complete object and closes the array.
    """
    # Find the last complete object by looking for the last "},"  or "}" before truncation
    last_complete = json_str.rfind("}")
    if last_complete == -1:
        raise ValueError(f"Cannot salvage LLM JSON. Fragment: {json_str[:300]}")

    candidate = json_str[: last_complete + 1].rstrip().rstrip(",") + "]"
    # Remove trailing commas again for safety
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)

    try:
        foods = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Cannot parse LLM JSON even after salvage attempt. Fragment: {json_str[:300]}"
        ) from exc

    return foods
