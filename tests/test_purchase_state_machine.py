"""Unit tests for the explicit purchase state machine.

These tests exercise the runner at the state-handler level, mocking only
the two external dependencies it has inside the loop (``_find_stamina_with_refresh``
and ``_match_with_retry``). That lets us verify each transition without
needing a real emulator, screen capture, or template library.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from staminabuyer.config import EmulatorTarget
from staminabuyer.pipeline import (
    CancelledError,
    PipelineOptions,
    PipelineRunner,
    PurchaseContext,
    PurchaseState,
    StaminaItem,
)
from staminabuyer.vision.matcher import MatchResult


def _fake_match(icon: str = "stamina_10") -> MatchResult:
    return MatchResult(
        icon=icon,
        score=1.0,
        top_left=(10, 10),
        bottom_right=(50, 70),
        scale=1.0,
    )


def _make_runner(**option_overrides) -> PipelineRunner:
    options = PipelineOptions(
        dry_run=False,
        max_retries=1,
        post_click_delay_seconds=0.0,
        post_purchase_delay_seconds=0.0,
        purchase_delay_seconds=0.0,
        jitter_seconds=0.0,
        **option_overrides,
    )
    runner = PipelineRunner(
        options=options,
        template_library=MagicMock(),  # bypass real template loading
        items=[StaminaItem("stamina_10", 500), StaminaItem("stamina_1", 50)],
    )
    return runner


@pytest.fixture
def client():
    return MagicMock(name="ScreenCaptureClient")


@pytest.fixture
def target():
    return EmulatorTarget(name="BlueStacks", stamina=500)


@pytest.fixture
def context(target):
    return PurchaseContext(target=target)


class TestPurchaseContext:
    def test_remaining_never_negative(self):
        target = EmulatorTarget(name="w", stamina=100)
        ctx = PurchaseContext(target=target, purchased=150)
        assert ctx.remaining == 0

    def test_is_satisfied_at_exact_target(self, target):
        ctx = PurchaseContext(target=target, purchased=500)
        assert ctx.is_satisfied

    def test_is_not_satisfied_below_target(self, target):
        ctx = PurchaseContext(target=target, purchased=499)
        assert not ctx.is_satisfied


class TestFocusWindowState:
    def test_focuses_and_transitions_to_find_item(self, client, context):
        runner = _make_runner()
        nxt = runner._state_focus_window(client, context)
        client.focus_window.assert_called_once()
        assert nxt is PurchaseState.FIND_ITEM


class TestFindItemState:
    def test_satisfied_context_goes_straight_to_done(self, client, target):
        runner = _make_runner()
        ctx = PurchaseContext(target=target, purchased=target.stamina)
        nxt = runner._state_find_item(client, ctx)
        assert nxt is PurchaseState.DONE

    def test_finds_item_and_populates_context(self, client, context, monkeypatch):
        runner = _make_runner()
        item = StaminaItem("stamina_10", 500)
        match = _fake_match()
        monkeypatch.setattr(
            runner, "_find_stamina_with_refresh", lambda c: (match, item)
        )

        nxt = runner._state_find_item(client, context)

        assert nxt is PurchaseState.TAP_ITEM
        assert context.pending_item is item
        assert context.pending_match is match
        assert context.purchase_count == 1


class TestTapItemState:
    def test_requires_pending_match(self, client, context):
        runner = _make_runner()
        with pytest.raises(AssertionError):
            runner._state_tap_item(client, context)

    def test_taps_and_transitions_to_wait(self, client, context, monkeypatch):
        runner = _make_runner()
        context.pending_match = _fake_match()
        tapped: list[MatchResult] = []
        monkeypatch.setattr(runner, "_tap_gem_button", lambda c, m: tapped.append(m))

        nxt = runner._state_tap_item(client, context)

        assert tapped == [context.pending_match]
        assert nxt is PurchaseState.WAIT_FOR_CONFIRM


class TestConfirmState:
    def test_success_transitions_to_record(self, client, context, monkeypatch):
        runner = _make_runner()
        confirm_match = _fake_match("to_confirm")
        monkeypatch.setattr(runner, "_match_with_retry", lambda c, name: confirm_match)
        tapped: list[MatchResult] = []
        monkeypatch.setattr(runner, "_tap_center", lambda c, m: tapped.append(m))

        nxt = runner._state_confirm(client, context)

        assert nxt is PurchaseState.RECORD_PURCHASE
        assert tapped == [confirm_match]

    def test_missing_dialog_clears_pending_and_restarts_find(
        self, client, context, monkeypatch
    ):
        """If no confirm dialog appears, we drop the pending selection and
        go back to FIND_ITEM rather than counting a fake purchase."""
        runner = _make_runner()
        context.pending_item = StaminaItem("stamina_10", 500)
        context.pending_match = _fake_match()

        def _raise(c, name):
            raise RuntimeError("no confirm button")

        monkeypatch.setattr(runner, "_match_with_retry", _raise)

        nxt = runner._state_confirm(client, context)

        assert nxt is PurchaseState.FIND_ITEM
        assert context.pending_item is None
        assert context.pending_match is None


class TestRecordPurchaseState:
    def test_adds_amount_and_fires_callback(self, client, target, monkeypatch):
        received: list[tuple[str, int]] = []
        runner = _make_runner()
        runner._progress_callback = lambda name, amt: received.append((name, amt))

        ctx = PurchaseContext(target=target)
        ctx.pending_item = StaminaItem("stamina_10", 500)

        nxt = runner._state_record_purchase(client, ctx)

        assert ctx.purchased == 500
        assert received == [(target.name, 500)]
        # Exactly at target → DONE
        assert nxt is PurchaseState.DONE
        assert ctx.pending_item is None
        assert ctx.pending_match is None

    def test_partial_progress_keeps_looping(self, client, monkeypatch):
        target = EmulatorTarget(name="w", stamina=1000)
        runner = _make_runner()
        ctx = PurchaseContext(target=target, purchased=500)
        ctx.pending_item = StaminaItem("stamina_10", 500)

        nxt = runner._state_record_purchase(client, ctx)

        assert ctx.purchased == 1000
        # Exactly at target → DONE (not FIND_ITEM) — guards off-by-one.
        assert nxt is PurchaseState.DONE

    def test_below_target_returns_to_find_item(self, client, monkeypatch):
        target = EmulatorTarget(name="w", stamina=1000)
        runner = _make_runner()
        ctx = PurchaseContext(target=target, purchased=0)
        ctx.pending_item = StaminaItem("stamina_1", 50)

        nxt = runner._state_record_purchase(client, ctx)

        assert ctx.purchased == 50
        assert nxt is PurchaseState.FIND_ITEM


class TestFullLoopDispatch:
    """Exercise the whole dispatcher end-to-end by mocking find+match."""

    def test_buys_until_target_is_met(self, monkeypatch):
        target = EmulatorTarget(name="w", stamina=1000)
        runner = _make_runner()

        client = MagicMock()
        monkeypatch.setattr(
            runner,
            "_find_stamina_with_refresh",
            lambda c: (_fake_match(), StaminaItem("stamina_10", 500)),
        )
        monkeypatch.setattr(runner, "_tap_gem_button", lambda c, m: None)
        monkeypatch.setattr(runner, "_tap_center", lambda c, m: None)
        monkeypatch.setattr(
            runner,
            "_match_with_retry",
            lambda c, name: _fake_match("to_confirm"),
        )

        purchased = runner._execute_purchase_loop(client, target)

        assert purchased == 1000
        client.focus_window.assert_called_once()

    def test_cancellation_mid_loop_raises_cancelled_error(self, monkeypatch):
        target = EmulatorTarget(name="w", stamina=1000)
        calls = {"n": 0}

        def cancel_after_first():
            calls["n"] += 1
            return calls["n"] > 1

        runner = _make_runner()
        runner._cancel_callback = cancel_after_first

        client = MagicMock()
        monkeypatch.setattr(
            runner,
            "_find_stamina_with_refresh",
            lambda c: (_fake_match(), StaminaItem("stamina_10", 500)),
        )
        monkeypatch.setattr(runner, "_tap_gem_button", lambda c, m: None)
        monkeypatch.setattr(runner, "_tap_center", lambda c, m: None)
        monkeypatch.setattr(
            runner, "_match_with_retry", lambda c, name: _fake_match("to_confirm")
        )

        with pytest.raises(CancelledError):
            runner._execute_purchase_loop(client, target)

    def test_missing_confirm_does_not_increment_purchased(self, monkeypatch):
        """Regression: confirm-dialog failures must not credit stamina."""
        target = EmulatorTarget(name="w", stamina=500)
        attempts = {"find": 0, "confirm": 0}

        def fake_find(c):
            attempts["find"] += 1
            return _fake_match(), StaminaItem("stamina_10", 500)

        def fake_confirm(c, name):
            attempts["confirm"] += 1
            if attempts["confirm"] == 1:
                # First attempt: no dialog → loop should retry.
                raise RuntimeError("no confirm")
            return _fake_match("to_confirm")

        runner = _make_runner()
        client = MagicMock()
        monkeypatch.setattr(runner, "_find_stamina_with_refresh", fake_find)
        monkeypatch.setattr(runner, "_tap_gem_button", lambda c, m: None)
        monkeypatch.setattr(runner, "_tap_center", lambda c, m: None)
        monkeypatch.setattr(runner, "_match_with_retry", fake_confirm)

        purchased = runner._execute_purchase_loop(client, target)

        # Exactly one successful purchase — the failed confirm didn't count.
        assert purchased == 500
        assert attempts["find"] == 2  # retried after the missing dialog
        assert attempts["confirm"] == 2
