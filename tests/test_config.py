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
