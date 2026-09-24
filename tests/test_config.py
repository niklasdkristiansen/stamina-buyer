from pathlib import Path

import pytest

from staminabuyer.config import ResolvedConfiguration, load_file_config, parse_target_argument, resolve_configuration


def test_parse_target_argument():
    target = parse_target_argument("LDPlayer-1:250")
    assert target.name == "LDPlayer-1"
    assert target.stamina == 250


def test_resolve_configuration_requires_targets(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("targets: []", encoding="utf-8")
    with pytest.raises(ValueError):
        resolve_configuration([], config_path)


def test_resolve_configuration_merge_cli(tmp_path: Path):
    config_path = tmp_path / "conf.yaml"
    config_path.write_text(
        """
        targets:
          - name: LDPlayer-1
            stamina: 200
        purchase_delay_seconds: 2
        jitter_seconds: 0.5
        """,
        encoding="utf-8",
    )

    resolved = resolve_configuration(["LDPlayer-2:100"], config_path)
    assert len(resolved.targets) == 2
    assert resolved.targets[0].name == "LDPlayer-1"
    assert resolved.targets[1].name == "LDPlayer-2"
    assert resolved.purchase_delay_seconds == 2
    assert resolved.jitter_seconds == 0.5


def test_parse_target_allows_colons_in_window_title():
    target = parse_target_argument("BlueStacks: Instance 2:300")
    assert target.name == "BlueStacks: Instance 2"
    assert target.stamina == 300


def test_config_file_may_hold_only_settings(tmp_path: Path):
    """Targets can come entirely from --target while the file supplies timing."""
    config_path = tmp_path / "timing.yaml"
    config_path.write_text("refresh_wait_seconds: 2.5\nauto_settle: false\n", encoding="utf-8")

    resolved = resolve_configuration(["BlueStacks:100"], config_path)

    assert [t.name for t in resolved.targets] == ["BlueStacks"]
    assert resolved.pipeline_overrides() == {"refresh_wait_seconds": 2.5, "auto_settle": False}


def test_cli_overrides_beat_file_and_unset_values_use_pipeline_defaults(tmp_path: Path):
    from staminabuyer.pipeline import PipelineOptions

    config_path = tmp_path / "timing.yaml"
    config_path.write_text(
        "targets:\n  - name: w\n    stamina: 50\nrefresh_wait_seconds: 2.5\nsettle_timeout_seconds: 4\n",
        encoding="utf-8",
    )

    resolved = resolve_configuration(
        [],
        config_path,
        cli_overrides={"refresh_wait_seconds": 3.0, "auto_settle": None, "settle_timeout_seconds": None},
    )
    options = PipelineOptions(**resolved.pipeline_overrides())

    assert options.refresh_wait_seconds == 3.0
    assert options.settle_timeout_seconds == 4
    assert options.auto_settle is PipelineOptions().auto_settle
    assert options.purchase_delay_seconds == PipelineOptions().purchase_delay_seconds


def test_negative_refresh_wait_is_rejected(tmp_path: Path):
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("targets: [{name: w, stamina: 1}]\nrefresh_wait_seconds: -1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        resolve_configuration([], config_path)
