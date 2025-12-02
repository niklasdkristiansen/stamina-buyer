"""Configuration helpers for the Stamina Buyer pipeline."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

TARGET_SEPARATOR = ":"


class EmulatorTarget(BaseModel):
    """Validated data describing how much stamina to buy in an emulator window."""

    name: str = Field(min_length=1)
    stamina: int = Field(gt=0, description="Total stamina to purchase in this run")


class FileConfig(BaseModel):
    """Schema for config files loaded from YAML/JSON."""

    targets: list[EmulatorTarget]
    purchase_delay_seconds: float = Field(default=1.0, ge=0.0)
    jitter_seconds: float = Field(default=0.2, ge=0.0)


@dataclass(slots=True)
class ResolvedConfiguration:
    """Merged runtime configuration."""

    targets: list[EmulatorTarget]
    purchase_delay_seconds: float
    jitter_seconds: float


def parse_target_argument(raw: str) -> EmulatorTarget:
    """Translate `name:stamina` CLI arguments into EmulatorTarget objects."""

    if TARGET_SEPARATOR not in raw:
        raise ValueError(
            f"Malformed target '{raw}'. Expected format '<emulator_name>{TARGET_SEPARATOR}<amount>'."
        )

    name, stamina_str = raw.split(TARGET_SEPARATOR, maxsplit=1)
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
    cli_targets: Sequence[str], config_path: Path | None
) -> ResolvedConfiguration:
    """Merge CLI targets with optional config file defaults."""

    parsed_cli = parse_targets(cli_targets)

    if config_path is None:
        if not parsed_cli:
            raise ValueError("Provide at least one --target or a config file with targets.")
        return ResolvedConfiguration(parsed_cli, purchase_delay_seconds=1.0, jitter_seconds=0.2)

    file_config = load_file_config(config_path)
    targets = file_config.targets or []
    if parsed_cli:
        targets.extend(parsed_cli)

    if not targets:
        raise ValueError("Resolved configuration contains no targets to process.")

    return ResolvedConfiguration(
        targets=targets,
        purchase_delay_seconds=file_config.purchase_delay_seconds,
        jitter_seconds=file_config.jitter_seconds,
    )
