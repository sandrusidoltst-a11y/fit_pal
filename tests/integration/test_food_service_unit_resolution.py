"""
Integration tests for the multi-unit resolver chain — exercised end-to-end
through the calculate_food_macros tool against a real Supabase test session.

Scope:
    Real DB rows; no LLM. Covers all 4 resolver branches.

LLM Usage:
    NONE.
"""
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

from tests.conftest import TEST_USER_A
from src.services.food_service import calculate_food_macros, create_food_item_record


def _patch_session(session):
    @asynccontextmanager
    async def _fake_session():
        yield session

    return patch("src.services.food_service.get_async_db_session", _fake_session)


async def _make_food(session, *, name_en, unit_weights, unit_synonyms):
    food, _ = await create_food_item_record(
        session=session,
        name_en=name_en,
        name_he=None,
        calories_per_100g=100.0,
        protein_per_100g=10.0,
        carbs_per_100g=10.0,
        fat_per_100g=5.0,
        user_id=TEST_USER_A,
        unit_weights=unit_weights,
        unit_synonyms=unit_synonyms,
        source="estimated",
    )
    return food


@pytest.mark.asyncio
async def test_curated_direct_hit(async_test_db_session):
    """
    arrange: food with unit_weights={"slice": 110}.
    act:     calculate_food_macros(count=2, unit="slice").
    assert:  amount_g == 220 (the direct lookup branch).
    """
    food = await _make_food(
        async_test_db_session,
        name_en="Resolver Pizza Direct",
        unit_weights={"slice": 110.0},
        unit_synonyms={},
    )

    with _patch_session(async_test_db_session):
        result = await calculate_food_macros.ainvoke(
            {"food_id": str(food.id), "count": 2.0, "unit": "slice"}
        )

    assert result["amount_g"] == 220.0
    assert result["calories"] == 220.0  # 100 cal/100g × 220g


@pytest.mark.asyncio
async def test_synonym_hit(async_test_db_session):
    """
    arrange: unit_weights={"slice": 110}, unit_synonyms={"piece": "slice"}.
    act:     calculate_food_macros with unit="piece".
    assert:  amount_g == 110 (resolved through synonym → canonical → weight).
    """
    food = await _make_food(
        async_test_db_session,
        name_en="Resolver Pizza Synonym",
        unit_weights={"slice": 110.0},
        unit_synonyms={"piece": "slice"},
    )

    with _patch_session(async_test_db_session):
        result = await calculate_food_macros.ainvoke(
            {"food_id": str(food.id), "count": 1.0, "unit": "piece"}
        )

    assert result["amount_g"] == 110.0


@pytest.mark.asyncio
async def test_uncurated_falls_back_to_estimate(async_test_db_session):
    """
    arrange: unit_weights={}, unit_synonyms={}.
    act:     calculate_food_macros with unit="bowl", llm_estimated_amount_g=350.
    assert:  amount_g == 350 (resolver's safety-net branch).
    """
    food = await _make_food(
        async_test_db_session,
        name_en="Resolver Bowl Estimate",
        unit_weights={},
        unit_synonyms={},
    )

    with _patch_session(async_test_db_session):
        result = await calculate_food_macros.ainvoke(
            {
                "food_id": str(food.id),
                "count": 1.0,
                "unit": "bowl",
                "llm_estimated_amount_g": 350.0,
            }
        )

    assert result["amount_g"] == 350.0


@pytest.mark.asyncio
async def test_uncurated_no_estimate_returns_count(async_test_db_session, caplog):
    """
    arrange: unit_weights={}, unit_synonyms={}; no llm_estimated_amount_g.
    act:     calculate_food_macros with unit="bowl".
    assert:  amount_g == count (last-resort fallback; resolver logs a warning).
    """
    food = await _make_food(
        async_test_db_session,
        name_en="Resolver Bowl No-Estimate",
        unit_weights={},
        unit_synonyms={},
    )

    with _patch_session(async_test_db_session):
        result = await calculate_food_macros.ainvoke(
            {"food_id": str(food.id), "count": 1.0, "unit": "bowl"}
        )

    assert result["amount_g"] == 1.0  # count flows through as-is, with a warning


@pytest.mark.asyncio
async def test_grams_passthrough(async_test_db_session):
    """
    arrange: food row exists; unit="g" should always passthrough regardless of curation.
    act:     calculate_food_macros(count=180, unit="g").
    assert:  amount_g == 180.
    """
    food = await _make_food(
        async_test_db_session,
        name_en="Resolver Grams Passthrough",
        unit_weights={"slice": 110.0},
        unit_synonyms={},
    )

    with _patch_session(async_test_db_session):
        result = await calculate_food_macros.ainvoke(
            {"food_id": str(food.id), "count": 180.0, "unit": "g"}
        )

    assert result["amount_g"] == 180.0
