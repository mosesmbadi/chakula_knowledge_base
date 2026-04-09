import asyncio
import json
import random
import re
from google import genai
from google.genai import errors as genai_errors, types
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
{exclude_section}
Region: {region}
Count: {count}"""


BATCH_SIZE = 50  # max foods per LLM call


class GeminiServiceUnavailableError(RuntimeError):
    pass


def _get_client() -> genai.Client:
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _candidate_models() -> list[str]:
    models = [settings.GEMINI_MODEL.strip()]
    fallback_model = settings.GEMINI_FALLBACK_MODEL.strip()
    if fallback_model and fallback_model not in models:
        models.append(fallback_model)
    return [model for model in models if model]


def _api_error_status_code(exc: genai_errors.APIError) -> int | None:
    return getattr(exc, "status_code", None) or getattr(exc, "code", None)


def _is_retryable_api_error(exc: genai_errors.APIError) -> bool:
    status_code = _api_error_status_code(exc)
    return status_code in {429, 500, 502, 503, 504} or isinstance(exc, genai_errors.ServerError)


def _retry_delay_seconds(attempt: int) -> float:
    base_delay = max(settings.GEMINI_RETRY_BASE_DELAY_SECONDS, 0.0)
    max_delay = max(settings.GEMINI_MAX_BACKOFF_SECONDS, base_delay or 1.0)
    jitter = random.uniform(0.0, 0.25)
    if base_delay == 0:
        return jitter
    return min(max_delay, (base_delay * (2 ** (attempt - 1))) + jitter)


async def _generate_batch_for_model(
    client: genai.Client,
    model_name: str,
    region: str,
    count: int,
    exclude_names: list[str] | None = None,
) -> list[dict]:
    """Single Gemini call for up to BATCH_SIZE foods. Retries transient API and parse failures."""
    if exclude_names:
        names_list = "\n".join(f"  - {n}" for n in exclude_names)
        exclude_section = f"\nDo NOT generate any of these already-generated foods:\n{names_list}\n"
    else:
        exclude_section = ""
    prompt = GENERATION_PROMPT.format(region=region, count=count, exclude_section=exclude_section)
    config = types.GenerateContentConfig(
        temperature=0.4,
        top_p=0.9,
        response_mime_type="application/json",
    )

    max_retries = max(settings.GEMINI_MAX_RETRIES, 1)

    for attempt in range(1, max_retries + 1):
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
        except genai_errors.APIError as exc:
            if not _is_retryable_api_error(exc) or attempt == max_retries:
                raise

            delay = _retry_delay_seconds(attempt)
            logger.warning(
                "Gemini request failed for model %s (attempt %d/%d, status=%s): %s. Retrying in %.2fs",
                model_name,
                attempt,
                max_retries,
                _api_error_status_code(exc),
                exc,
                delay,
            )
            await asyncio.sleep(delay)
            continue

        raw = response.text or ""

        try:
            return _parse_llm_response(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            delay = _retry_delay_seconds(attempt)
            logger.warning(
                "LLM JSON parse failed for model %s (attempt %d/%d): %s\nRaw (first 500 chars): %s",
                model_name, attempt, max_retries, exc, raw[:500],
            )
            if attempt == max_retries:
                raise
            await asyncio.sleep(delay)

    raise RuntimeError("Gemini batch generation exited unexpectedly")


async def _generate_batch(client: genai.Client, region: str, count: int, exclude_names: list[str] | None = None) -> list[dict]:
    candidate_models = _candidate_models()
    if not candidate_models:
        raise RuntimeError("No Gemini model configured. Set GEMINI_MODEL in the environment.")

    last_retryable_error: genai_errors.APIError | None = None
    last_parse_error: Exception | None = None

    for model_name in candidate_models:
        try:
            return await _generate_batch_for_model(
                client=client,
                model_name=model_name,
                region=region,
                count=count,
                exclude_names=exclude_names,
            )
        except genai_errors.APIError as exc:
            if not _is_retryable_api_error(exc):
                raise

            last_retryable_error = exc
            logger.warning(
                "Gemini model %s remained unavailable after %d attempts. Trying next model if configured.",
                model_name,
                max(settings.GEMINI_MAX_RETRIES, 1),
            )
        except (json.JSONDecodeError, ValueError) as exc:
            last_parse_error = exc
            logger.warning(
                "Gemini model %s returned unusable JSON after %d attempts. Trying next model if configured.",
                model_name,
                max(settings.GEMINI_MAX_RETRIES, 1),
            )

    if last_retryable_error is not None:
        model_list = ", ".join(candidate_models)
        raise GeminiServiceUnavailableError(
            f"Gemini is temporarily unavailable for configured model(s): {model_list}. Please retry shortly."
        ) from last_retryable_error

    if last_parse_error is not None:
        raise ValueError("Gemini returned invalid JSON after exhausting all configured models.") from last_parse_error

    raise RuntimeError("Gemini batch generation failed before any model attempt completed")


async def generate_foods_from_llm(region: str, count: int) -> list[dict]:
    """
    Call the Gemini API and parse the structured food list it returns.
    Large counts are split into batches, with each batch told to avoid
    names already generated in previous batches.
    """
    client = _get_client()
    all_foods: list[dict] = []
    generated_names: list[str] = []

    remaining = count
    while remaining > 0:
        batch = min(remaining, BATCH_SIZE)
        foods = await _generate_batch(client, region, batch, exclude_names=generated_names or None)
        all_foods.extend(foods)
        generated_names.extend(f["name"] for f in foods if "name" in f)
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
