import json
import logging
import sys
import urllib.parse
import urllib.request
from typing import Any

from mcp.server import MCPServer


# ---------------------------------------------------------
# MCP SERVER CONFIGURATION
# ---------------------------------------------------------

mcp = MCPServer("meals")

BASE_URL = "https://www.themealdb.com/api/json/v1/1/"


# STDIO MCP servers must not log to stdout.
logger = logging.getLogger("meals_server")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s"
)
handler.setFormatter(formatter)

logger.addHandler(handler)


# ---------------------------------------------------------
# HTTP HELPER
# ---------------------------------------------------------

def fetch_json(endpoint: str, params: dict[str, Any] | None = None):
    """
    Call TheMealDB and return decoded JSON.

    Raises a clean RuntimeError for network or JSON failures.
    """

    url = BASE_URL + endpoint

    if params:
        url += "?" + urllib.parse.urlencode(params)

    try:
        with urllib.request.urlopen(
            url,
            timeout=10
        ) as response:
            body = response.read().decode("utf-8")

        return json.loads(body)

    except Exception as exc:
        logger.error("TheMealDB request failed: %s", exc)

        raise RuntimeError(
            "Unable to retrieve data from TheMealDB."
        ) from exc


# ---------------------------------------------------------
# RECIPE FORMATTER
# ---------------------------------------------------------

def format_meal_details(meal: dict[str, Any]):
    ingredients = []

    for index in range(1, 21):
        ingredient = meal.get(f"strIngredient{index}")
        measure = meal.get(f"strMeasure{index}")

        if ingredient and ingredient.strip():
            ingredients.append(
                {
                    "name": ingredient.strip(),
                    "measure": (
                        measure.strip()
                        if measure
                        else ""
                    ),
                }
            )

    return {
        "id": meal.get("idMeal"),
        "name": meal.get("strMeal"),
        "category": meal.get("strCategory"),
        "area": meal.get("strArea"),
        "instructions": meal.get("strInstructions"),
        "image": meal.get("strMealThumb"),
        "source": meal.get("strSource"),
        "youtube": meal.get("strYoutube"),
        "ingredients": ingredients,
    }


# ---------------------------------------------------------
# TOOL 1
# Search meals by name
# ---------------------------------------------------------

@mcp.tool()
def search_meals_by_name(
    query: str,
    limit: int = 5
):
    """
    Search for meals by meal name.
    """

    query = query.strip()

    if not query:
        raise ValueError("query must not be empty")

    if limit < 1 or limit > 25:
        raise ValueError(
            "limit must be between 1 and 25"
        )

    result = fetch_json(
        "search.php",
        {"s": query}
    )

    meals = result.get("meals")

    if meals is None:
        return {
            "message": "no matches",
            "results": []
        }

    return [
        {
            "id": meal.get("idMeal"),
            "name": meal.get("strMeal"),
            "area": meal.get("strArea"),
            "category": meal.get("strCategory"),
            "thumb": meal.get("strMealThumb"),
        }
        for meal in meals[:limit]
    ]


# ---------------------------------------------------------
# TOOL 2
# Search meals by main ingredient
# ---------------------------------------------------------

@mcp.tool()
def meals_by_ingredient(
    ingredient: str,
    limit: int = 12
):
    """
    Search for meals containing a main ingredient.
    """

    ingredient = ingredient.strip()

    if not ingredient:
        raise ValueError(
            "ingredient must not be empty"
        )

    if limit < 1 or limit > 25:
        raise ValueError(
            "limit must be between 1 and 25"
        )

    result = fetch_json(
        "filter.php",
        {"i": ingredient}
    )

    meals = result.get("meals")

    if meals is None:
        return {
            "message": "no matches",
            "results": []
        }

    return [
        {
            "id": meal.get("idMeal"),
            "name": meal.get("strMeal"),
            "thumb": meal.get("strMealThumb"),
        }
        for meal in meals[:limit]
    ]


# ---------------------------------------------------------
# TOOL 3
# Random meal
# ---------------------------------------------------------

@mcp.tool()
def random_meal():
    """
    Return one random meal with full recipe details.
    """

    result = fetch_json("random.php")

    meals = result.get("meals")

    if not meals:
        return {
            "message": "no matches",
            "result": None
        }

    return format_meal_details(meals[0])


# ---------------------------------------------------------
# TOOL 4
# Meal details by ID
# ---------------------------------------------------------

@mcp.tool()
def meal_details(id: str):
    """
    Return full recipe details for a meal ID.
    """

    meal_id = str(id).strip()

    if not meal_id:
        raise ValueError(
            "id must not be empty"
        )

    result = fetch_json(
        "lookup.php",
        {"i": meal_id}
    )

    meals = result.get("meals")

    if not meals:
        return {
            "message": "no matches",
            "result": None
        }

    return format_meal_details(meals[0])


# ---------------------------------------------------------
# SERVER ENTRY POINT
# ---------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting meals MCP server")
    mcp.run()