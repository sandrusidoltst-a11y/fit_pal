"""User-facing string i18n for the FitPal bot and graph nodes.

The Messages TypedDict is the single source of truth for what keys the
system needs. en.yaml and he.yaml must contain exactly those keys, with
non-empty string values. The parity check runs at module import time
and refuses to boot the process on any drift.

Pick the active language with the BOT_LANGUAGE env var ("en" default,
"he" supported). Both the langgraph-server and fitpal-bot processes
import this module independently — set BOT_LANGUAGE on both Railway
services or you'll get half-translated chats.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict, get_type_hints

import structlog
import yaml

logger = structlog.get_logger(__name__)

I18N_DIR = Path(__file__).parent
EN_FILE = I18N_DIR / "en.yaml"
HE_FILE = I18N_DIR / "he.yaml"

SUPPORTED_LANGS = ("en", "he")
DEFAULT_LANG = "en"


class Messages(TypedDict):
    # Onboarding
    onboarding_welcome: str
    onboarding_welcome_back: str
    onboarding_complete: str
    onboarding_q_name: str
    onboarding_q_height: str
    onboarding_q_age: str
    onboarding_q_gender: str
    onboarding_invalid_height: str
    onboarding_invalid_age: str
    onboarding_invalid_gender: str
    # Auth / passphrase
    auth_invite_prompt: str
    auth_registration_error: str
    # Errors
    error_generic_thread: str
    error_generic_request: str
    error_empty_response: str
    error_non_text: str
    # HITL confirmation (graph node payload)
    confirmation_question: str
    confirmation_estimated_tag: str
    # HITL confirmation render (bot)
    confirmation_macro_line: str
    confirmation_total_line: str
    confirmation_reply_hint: str
    # HITL serving info (bot-rendered per item)
    confirmation_serving_line: str
    confirmation_category_label_protein: str
    confirmation_category_label_carb: str
    confirmation_category_label_fat: str
    confirmation_category_label_free: str
    confirmation_category_label_free_calories: str
    confirmation_category_label_forbidden_main: str
    # HITL date label (bot-rendered when consumed_at is set)
    confirmation_date_for: str
    confirmation_date_today: str
    confirmation_date_yesterday: str
    confirmation_date_other: str
    # HITL unit labels (bot-rendered in preview when original_unit != "g")
    confirmation_unit_label_bottle_singular: str
    confirmation_unit_label_bottle_plural: str
    confirmation_unit_label_can_singular: str
    confirmation_unit_label_can_plural: str
    confirmation_unit_label_cup_singular: str
    confirmation_unit_label_cup_plural: str
    confirmation_unit_label_piece_singular: str
    confirmation_unit_label_piece_plural: str
    confirmation_unit_label_scoop_singular: str
    confirmation_unit_label_scoop_plural: str
    confirmation_unit_label_slice_singular: str
    confirmation_unit_label_slice_plural: str
    confirmation_unit_label_tbsp_singular: str
    confirmation_unit_label_tbsp_plural: str
    confirmation_unit_label_tsp_singular: str
    confirmation_unit_label_tsp_plural: str


# Derive the expected key set from the TypedDict so adding a new field
# automatically requires both YAMLs to add it.
EXPECTED_KEYS: frozenset[str] = frozenset(get_type_hints(Messages).keys())


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"i18n file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(
            f"i18n file must be a flat mapping at top level, got {type(data).__name__}: {path}"
        )
    return data


def _validate_parity(en: dict, he: dict, expected_keys: frozenset[str]) -> None:
    """Collect every parity violation and raise once with the full picture."""
    en_keys = set(en.keys())
    he_keys = set(he.keys())

    en_missing = expected_keys - en_keys
    he_missing = expected_keys - he_keys
    en_extra = en_keys - expected_keys
    he_extra = he_keys - expected_keys

    en_empty = sorted(k for k in (expected_keys & en_keys) if not _is_non_empty_str(en[k]))
    he_empty = sorted(k for k in (expected_keys & he_keys) if not _is_non_empty_str(he[k]))

    errors: list[str] = []
    if en_missing:
        errors.append(f"en.yaml missing keys: {sorted(en_missing)}")
    if he_missing:
        errors.append(f"he.yaml missing keys: {sorted(he_missing)}")
    if en_extra:
        errors.append(f"en.yaml has keys not in Messages TypedDict: {sorted(en_extra)}")
    if he_extra:
        errors.append(f"he.yaml has keys not in Messages TypedDict: {sorted(he_extra)}")
    if en_empty:
        errors.append(
            f"en.yaml keys with empty/non-string values: {en_empty} — "
            "set them or use the English fallback"
        )
    if he_empty:
        errors.append(
            f"he.yaml keys with empty/non-string values: {he_empty} — "
            "set them or use the English fallback"
        )

    if errors:
        raise ValueError("i18n parity check failed:\n  " + "\n  ".join(errors))


def _is_non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value != ""


def _resolve_language(raw: str | None) -> str:
    """Lowercase and validate against SUPPORTED_LANGS. None falls back to DEFAULT_LANG."""
    if raw is None:
        return DEFAULT_LANG
    lang = raw.lower()
    if lang not in SUPPORTED_LANGS:
        raise ValueError(
            f"Unsupported BOT_LANGUAGE={raw!r}; must be one of {SUPPORTED_LANGS}"
        )
    return lang


def _load_messages_from_paths(en_path: Path, he_path: Path, lang: str) -> Messages:
    """Pure function — load both YAMLs, validate parity, return the chosen language dict.

    Tests call this directly with fixture paths; the module-level loader uses the
    real EN_FILE / HE_FILE / BOT_LANGUAGE env var.
    """
    en = _load_yaml(en_path)
    he = _load_yaml(he_path)
    _validate_parity(en, he, EXPECTED_KEYS)
    chosen = he if lang == "he" else en
    return chosen  # type: ignore[return-value]


def _load_messages() -> Messages:
    raw = os.environ.get("BOT_LANGUAGE")
    lang = _resolve_language(raw)
    messages = _load_messages_from_paths(EN_FILE, HE_FILE, lang)
    logger.info("i18n loaded", language=lang, key_count=len(messages))
    return messages


MESSAGES: Messages = _load_messages()
