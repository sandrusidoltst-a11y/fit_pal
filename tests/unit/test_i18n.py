"""Unit tests for the i18n loader and parity check.

Scope:
    Pure-function tests against fixture YAMLs in tmp_path. No DB, no network.
    Validates parity rules, env-var resolution, and placeholder preservation.

LLM Usage:
    NONE.
"""

from pathlib import Path

import pytest
import yaml

from src.i18n import (
    DEFAULT_LANG,
    EXPECTED_KEYS,
    MESSAGES,
    SUPPORTED_LANGS,
    Messages,
    _load_messages_from_paths,
    _resolve_language,
    _validate_parity,
)


def _write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def _full_dict(prefix: str = "") -> dict[str, str]:
    """Build a dict with every expected key populated with a non-empty value."""
    return {key: f"{prefix}{key}" for key in EXPECTED_KEYS}


class TestResolveLanguage:
    """Tests for the BOT_LANGUAGE env var resolution."""

    def test_none_falls_back_to_default(self):
        """
        arrange: no env var.
        act:     resolve None.
        assert:  returns DEFAULT_LANG.
        """
        assert _resolve_language(None) == DEFAULT_LANG

    def test_supported_language_lowercased(self):
        """
        arrange: uppercase 'EN'.
        act:     resolve.
        assert:  returns 'en'.
        """
        assert _resolve_language("EN") == "en"
        assert _resolve_language("HE") == "he"

    def test_supported_language_passthrough(self):
        """
        arrange: each supported lang.
        act:     resolve.
        assert:  returned verbatim.
        """
        for lang in SUPPORTED_LANGS:
            assert _resolve_language(lang) == lang

    def test_unsupported_language_raises(self):
        """
        arrange: 'fr'.
        act:     resolve.
        assert:  ValueError mentions BOT_LANGUAGE and the offending value.
        """
        with pytest.raises(ValueError, match="BOT_LANGUAGE.*fr"):
            _resolve_language("fr")

    def test_empty_string_raises(self):
        """
        arrange: explicitly empty env var.
        act:     resolve.
        assert:  ValueError — explicit empty string is not silently defaulted.
        """
        with pytest.raises(ValueError, match="BOT_LANGUAGE"):
            _resolve_language("")


class TestValidateParity:
    """Tests for the parity check across en.yaml and he.yaml."""

    def test_passes_when_keysets_match(self):
        """
        arrange: en and he with identical full key sets, all non-empty.
        act:     validate parity.
        assert:  no exception.
        """
        en = _full_dict("en_")
        he = _full_dict("he_")
        _validate_parity(en, he, EXPECTED_KEYS)

    def test_fails_when_he_missing_key(self):
        """
        arrange: he missing one expected key.
        act:     validate.
        assert:  ValueError lists the missing key under he.
        """
        en = _full_dict("en_")
        he = _full_dict("he_")
        sample_key = next(iter(EXPECTED_KEYS))
        del he[sample_key]
        with pytest.raises(ValueError, match=f"he.yaml missing keys.*{sample_key}"):
            _validate_parity(en, he, EXPECTED_KEYS)

    def test_fails_when_en_missing_key(self):
        """
        arrange: en missing one expected key.
        act:     validate.
        assert:  ValueError lists the missing key under en.
        """
        en = _full_dict("en_")
        he = _full_dict("he_")
        sample_key = next(iter(EXPECTED_KEYS))
        del en[sample_key]
        with pytest.raises(ValueError, match=f"en.yaml missing keys.*{sample_key}"):
            _validate_parity(en, he, EXPECTED_KEYS)

    def test_fails_when_en_has_extra_key(self):
        """
        arrange: en includes a key not in the TypedDict.
        act:     validate.
        assert:  ValueError mentions the extra key.
        """
        en = _full_dict("en_")
        he = _full_dict("he_")
        en["bogus_extra_key"] = "x"
        with pytest.raises(ValueError, match="en.yaml has keys not in.*bogus_extra_key"):
            _validate_parity(en, he, EXPECTED_KEYS)

    def test_fails_when_he_has_extra_key(self):
        """
        arrange: he includes a key not in the TypedDict.
        act:     validate.
        assert:  ValueError mentions the extra key.
        """
        en = _full_dict("en_")
        he = _full_dict("he_")
        he["bogus_extra_key"] = "x"
        with pytest.raises(ValueError, match="he.yaml has keys not in.*bogus_extra_key"):
            _validate_parity(en, he, EXPECTED_KEYS)

    def test_fails_on_empty_string_value(self):
        """
        arrange: he has an empty string for one key.
        act:     validate.
        assert:  ValueError mentions empty value and the key.
        """
        en = _full_dict("en_")
        he = _full_dict("he_")
        sample_key = next(iter(EXPECTED_KEYS))
        he[sample_key] = ""
        with pytest.raises(ValueError, match=f"he.yaml keys with empty.*{sample_key}"):
            _validate_parity(en, he, EXPECTED_KEYS)

    def test_fails_on_non_string_value(self):
        """
        arrange: en has a non-string (int) value for one key.
        act:     validate.
        assert:  ValueError mentions empty/non-string and the key.
        """
        en = _full_dict("en_")
        he = _full_dict("he_")
        sample_key = next(iter(EXPECTED_KEYS))
        en[sample_key] = 123  # type: ignore[assignment]
        with pytest.raises(ValueError, match=f"en.yaml keys with empty.*{sample_key}"):
            _validate_parity(en, he, EXPECTED_KEYS)

    def test_collects_multiple_violations_in_one_error(self):
        """
        arrange: en missing key A, he has empty value for key B.
        act:     validate.
        assert:  single ValueError mentions both violations.
        """
        en = _full_dict("en_")
        he = _full_dict("he_")
        keys = list(EXPECTED_KEYS)
        del en[keys[0]]
        he[keys[1]] = ""
        with pytest.raises(ValueError) as exc:
            _validate_parity(en, he, EXPECTED_KEYS)
        msg = str(exc.value)
        assert "en.yaml missing keys" in msg
        assert "he.yaml keys with empty" in msg
        assert keys[0] in msg
        assert keys[1] in msg


class TestLoadMessagesFromPaths:
    """Tests for the pure loader function."""

    def test_loads_english_when_lang_en(self, tmp_path):
        """
        arrange: fixture yamls with prefixed values, lang='en'.
        act:     load.
        assert:  returns en values.
        """
        en_path = _write_yaml(tmp_path / "en.yaml", _full_dict("en_"))
        he_path = _write_yaml(tmp_path / "he.yaml", _full_dict("he_"))
        sample_key = next(iter(EXPECTED_KEYS))

        result = _load_messages_from_paths(en_path, he_path, "en")

        assert result[sample_key] == f"en_{sample_key}"  # type: ignore[literal-required]

    def test_loads_hebrew_when_lang_he(self, tmp_path):
        """
        arrange: fixture yamls, lang='he'.
        act:     load.
        assert:  returns he values.
        """
        en_path = _write_yaml(tmp_path / "en.yaml", _full_dict("en_"))
        he_path = _write_yaml(tmp_path / "he.yaml", _full_dict("he_"))
        sample_key = next(iter(EXPECTED_KEYS))

        result = _load_messages_from_paths(en_path, he_path, "he")

        assert result[sample_key] == f"he_{sample_key}"  # type: ignore[literal-required]

    def test_raises_when_yaml_missing(self, tmp_path):
        """
        arrange: only en.yaml exists, he.yaml missing.
        act:     load.
        assert:  FileNotFoundError mentions he.yaml path.
        """
        en_path = _write_yaml(tmp_path / "en.yaml", _full_dict("en_"))
        he_path = tmp_path / "he.yaml"  # not created

        with pytest.raises(FileNotFoundError, match="he.yaml"):
            _load_messages_from_paths(en_path, he_path, "en")

    def test_raises_when_yaml_is_list_not_dict(self, tmp_path):
        """
        arrange: en.yaml is a YAML list, not a mapping.
        act:     load.
        assert:  ValueError mentions 'flat mapping'.
        """
        en_path = tmp_path / "en.yaml"
        en_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
        he_path = _write_yaml(tmp_path / "he.yaml", _full_dict("he_"))

        with pytest.raises(ValueError, match="flat mapping"):
            _load_messages_from_paths(en_path, he_path, "en")


class TestRealMessagesModule:
    """Tests for the actual module-level MESSAGES loaded from src/i18n/*.yaml."""

    def test_messages_has_all_expected_keys(self):
        """
        arrange: production load (default BOT_LANGUAGE=en).
        act:     read MESSAGES.
        assert:  every expected key is present.
        """
        for key in EXPECTED_KEYS:
            assert key in MESSAGES, f"missing key in MESSAGES: {key}"

    def test_placeholder_preservation_onboarding_complete(self):
        """
        arrange: MESSAGES['onboarding_complete'] has a {name} placeholder.
        act:     format with name='Dolev'.
        assert:  output contains 'Dolev' and no literal '{name}'.
        """
        formatted = MESSAGES["onboarding_complete"].format(name="Dolev")
        assert "Dolev" in formatted
        assert "{name}" not in formatted

    def test_placeholder_preservation_macro_line(self):
        """
        arrange: MESSAGES['confirmation_macro_line'] has cals/protein/carbs/fat placeholders.
        act:     format with sample values.
        assert:  numeric values appear, no leftover placeholder syntax.
        """
        formatted = MESSAGES["confirmation_macro_line"].format(
            cals=330, protein=62, carbs=0, fat=7.2
        )
        assert "330" in formatted
        assert "62" in formatted
        assert "{cals}" not in formatted
        assert "{protein}" not in formatted

    def test_messages_typeddict_matches_yaml_keys(self):
        """
        arrange: TypedDict-derived EXPECTED_KEYS and the loaded MESSAGES.
        act:     compare.
        assert:  keysets are equal.
        """
        assert set(MESSAGES.keys()) == EXPECTED_KEYS

    def test_messages_typeddict_class(self):
        """
        arrange: Messages TypedDict.
        act:     check it's a class with __annotations__.
        assert:  has expected annotation count.
        """
        assert hasattr(Messages, "__annotations__")
        assert len(Messages.__annotations__) == len(EXPECTED_KEYS)
