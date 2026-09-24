"""Configuration helpers for the Stamina Buyer pipeline."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

TARGET_SEPARATOR = ":"

#: Settings a config file or CLI flag may override. Anything left unset
#: falls back to the ``PipelineOptions`` default.
PIPELINE_OVERRIDE_FIELDS = (
    "purchase_delay_seconds",
    "jitter_seconds",
    "refresh_wait_seconds",
    "auto_settle",
    "settle_timeout_seconds",
)


class EmulatorTarget(BaseModel):
    """Validated data describing how much stamina to buy in an emulator window."""

    name: str = Field(min_length=1)
    stamina: int = Field(gt=0, description="Total stamina to purchase in this run")


class FileConfig(BaseModel):
    """Schema for config files loaded from YAML/JSON."""

    targets: list[EmulatorTarget] = Field(default_factory=list)
    purchase_delay_seconds: float | None = Field(default=None, ge=0.0)
    jitter_seconds: float | None = Field(default=None, ge=0.0)
    refresh_wait_seconds: float | None = Field(default=None, ge=0.0)
    auto_settle: bool | None = None
    settle_timeout_seconds: float | None = Field(default=None, gt=0.0)


@dataclass(slots=True)
class ResolvedConfiguration:
    """Merged runtime configuration. ``None`` means "use the pipeline default"."""

    targets: list[EmulatorTarget]
    purchase_delay_seconds: float | None = None
    jitter_seconds: float | None = None
    refresh_wait_seconds: float | None = None
    auto_settle: bool | None = None
    settle_timeout_seconds: float | None = None

    def pipeline_overrides(self) -> dict[str, float | bool]:
        """Explicitly-set settings, as keyword arguments for ``PipelineOptions``."""
        return {
            name: getattr(self, name)
            for name in PIPELINE_OVERRIDE_FIELDS
            if getattr(self, name) is not None
        }


def parse_target_argument(raw: str) -> EmulatorTarget:
    """Translate `name:stamina` CLI arguments into EmulatorTarget objects."""

    if TARGET_SEPARATOR not in raw:
        raise ValueError(
            f"Malformed target '{raw}'. Expected format '<emulator_name>{TARGET_SEPARATOR}<amount>'."
        )

    # Split on the last separator so window titles may themselves contain ':'.
    name, stamina_str = raw.rsplit(TARGET_SEPARATOR, maxsplit=1)
    try:
        stamina = int(stamina_str)
    except ValueError as exc:  # pragma: no cover - defensive branch
        raise ValueError(f"Stamina amount must be an integer, got '{stamina_str}'.") from exc

    return EmulatorTarget(name=name.strip(), stamina=stamina)


def parse_targets(arguments: Sequence[str]) -> list[EmulatorTarget]:
    """Parse all CLI target entries."""

    return [parse_target_argument(arg) for arg in arguments]


def load_file_config(path: Path) -> FileConfig:
    """Load YAML/JSON config files and validate them."""

    if not path.exists():
        raise FileNotFoundError(path)

    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(content) or {}
    else:
        payload = json.loads(content)

    try:
        return FileConfig.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Config file {path} is invalid: {exc}") from exc


def resolve_configuration(
    cli_targets: Sequence[str],
    config_path: Path | None,
    cli_overrides: Mapping[str, float | bool | None] | None = None,
) -> ResolvedConfiguration:
    """Merge CLI targets and settings with an optional config file.

    CLI targets are added to the file's targets; CLI settings that are not
    ``None`` take precedence over the file's.
    """

    file_config = load_file_config(config_path) if config_path is not None else FileConfig()
    targets = [*file_config.targets, *parse_targets(cli_targets)]
    if not targets:
        raise ValueError("Provide at least one --target or a config file with targets.")

    settings = {name: getattr(file_config, name) for name in PIPELINE_OVERRIDE_FIELDS}
    for name, value in (cli_overrides or {}).items():
        if name not in settings:
            raise ValueError(f"Unknown setting '{name}'.")
        if value is not None:
            settings[name] = value

    return ResolvedConfiguration(targets=targets, **settings)
