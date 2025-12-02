"""Thin wrapper around the `adb` command-line tool."""

from __future__ import annotations

import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


class ADBError(RuntimeError):
    """Raised when an adb command exits abnormally."""


@dataclass(slots=True)
class ADBClient:
    serial: str | None = None
    adb_path: str = "adb"
    timeout: float | None = 10.0

    def _base_command(self) -> list[str]:
        cmd = [self.adb_path]
        if self.serial:
            cmd.extend(["-s", self.serial])
        return cmd

    def _run(self, extra: Sequence[str], capture_output: bool = False) -> subprocess.CompletedProcess:
        cmd = [*self._base_command(), *extra]
        completed = subprocess.run(  # noqa: S603,S607 - user-provided executable
            cmd,
            capture_output=capture_output,
            check=False,
            text=False,
            timeout=self.timeout,
        )
        if completed.returncode != 0:
            raise ADBError(
                f"adb command failed ({completed.returncode}): {' '.join(cmd)}",
            )
        return completed

    def shell(self, args: Iterable[str]) -> None:
        self._run(["shell", *args])

    def tap(self, x: int, y: int) -> None:
        self.shell(["input", "tap", str(x), str(y)])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.shell(["input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)])

    def send_keyevent(self, keycode: str) -> None:
        self.shell(["input", "keyevent", keycode])

    def screencap(self) -> bytes:
        return self._run(["exec-out", "screencap", "-p"], capture_output=True).stdout
