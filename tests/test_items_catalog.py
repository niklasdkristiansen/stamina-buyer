"""Tests for the YAML-driven stamina item catalog."""

from __future__ import annotations

from pathlib import Path

import pytest

from staminabuyer.pipeline import (
    DEFAULT_STAMINA_ITEMS,
    StaminaItem,
    load_stamina_items,
)


def test_bundled_items_file_matches_defaults():
    """The shipped assets/items.yaml should be equivalent to the hard-coded defaults."""
    repo_root = Path(__file__).resolve().parent.parent
    bundled = load_stamina_items(repo_root / "assets" / "items.yaml")

    assert [(i.template_name, i.stamina_amount) for i in bundled] == [
        (i.template_name, i.stamina_amount) for i in DEFAULT_STAMINA_ITEMS
    ]


def test_load_nonexistent_path_returns_defaults(tmp_path: Path):
    result = load_stamina_items(tmp_path / "does_not_exist.yaml")
    assert result == list(DEFAULT_STAMINA_ITEMS)


def test_load_custom_catalog(tmp_path: Path):
    path = tmp_path / "custom.yaml"
    path.write_text(
        """
        items:
          - template: stamina_1
            amount: 50
          - template: stamina_10
            amount: 500
        """,
        encoding="utf-8",
    )

    result = load_stamina_items(path)

    assert result == [
        StaminaItem("stamina_1", 50),
        StaminaItem("stamina_10", 500),
    ]


def test_load_preserves_priority_order(tmp_path: Path):
    """Order in the YAML is the order the pipeline will try items in."""
    path = tmp_path / "custom.yaml"
    path.write_text(
        """
        items:
          - template: tier_c
            amount: 10
          - template: tier_a
            amount: 1000
          - template: tier_b
            amount: 100
        """,
        encoding="utf-8",
    )

    result = load_stamina_items(path)
    assert [i.template_name for i in result] == ["tier_c", "tier_a", "tier_b"]


@pytest.mark.parametrize(
    "yaml_body,expected_msg",
    [
        ("items: []", "non-empty 'items:' list"),
        ("{}", "non-empty 'items:' list"),
        (
            """
            items:
              - template: stamina_10
            """,
            "missing required field",
        ),
        (
            """
            items:
              - template: stamina_10
                amount: 0
            """,
            "must be positive",
        ),
        (
            """
            items:
              - "not a mapping"
            """,
            "must be a mapping",
        ),
    ],
)
def test_invalid_catalogs_raise(tmp_path: Path, yaml_body: str, expected_msg: str):
    path = tmp_path / "bad.yaml"
    path.write_text(yaml_body, encoding="utf-8")

    with pytest.raises(ValueError, match=expected_msg):
        load_stamina_items(path)


def test_pipeline_runner_accepts_explicit_items(tmp_path: Path, monkeypatch):
    """The runner should honor the `items=` kwarg even when the YAML exists."""
    # Avoid touching real screen-capture code by stubbing out the template library.
    from staminabuyer.pipeline import PipelineOptions, PipelineRunner

    class _StubTemplates:
        def has_template(self, name):
            return True

    options = PipelineOptions(dry_run=True)
    explicit = [StaminaItem("custom_item", 42)]

    runner = PipelineRunner(
        options=options,
        template_library=_StubTemplates(),  # type: ignore[arg-type]
        items=explicit,
    )

    assert runner._items == explicit
