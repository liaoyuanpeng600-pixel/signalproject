"""Tests for CalibrationEmitter (Phase 5 Checkpoint 3)."""

import json

import pytest

from src.core.entities import Entity, EntityKind
from src.core.ids import ID
from src.core.invariants import Score
from src.core.signals import EntityRef, Signal, SignalDirection, SignalHorizon
from src.persistence.in_memory import InMemoryStore
from src.persistence.override import OverrideAction, OverrideRecord
from src.research.calibration import CalibrationData, CalibrationEmitter, ScoreDelta
from src.research.conflicts import ConflictEvent, ConflictKind
from src.research.themes import ThemePath


# ----------------------- helpers -----------------------


def _score(value: float) -> Score:
    return Score(value, value, value, value, value)


def _signal(signal_id: str, composite: float = 0.7) -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id="e-1", kind="company"),
        type="capital_action",
        claim=f"claim {signal_id}",
        evidence_ids=(ID(f"ev-{signal_id}"),),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=_score(composite),
        id=ID(signal_id),
    )


def _record(
    *,
    target_id: str,
    action: OverrideAction,
    payload: dict[str, object] | None = None,
) -> OverrideRecord:
    return OverrideRecord.create(
        target_id=ID(target_id),
        action=action,
        rationale="r",
        actor="curator:test",
        payload=payload,
    )


def _conflict(kind: ConflictKind, target: str = "t-1") -> ConflictEvent:
    return ConflictEvent(
        kind=kind,
        target_id=ID(target),
        rationale="r",
        contributing_record_ids=(ID("r-1"),),
        at="2026-07-19T00:00:00Z",
    )


# ----------------------- empty inputs -----------------------


class TestEmptyInputs:
    def test_emit_with_no_inputs(self) -> None:
        emitter = CalibrationEmitter()
        data = emitter.emit(cycle_id="c-1", overrides=(), conflicts=(), theme_paths=())
        assert isinstance(data, CalibrationData)
        assert data.cycle_id == "c-1"
        assert data.total_signals == 0
        assert data.total_overrides == 0
        assert data.total_conflicts == 0
        assert data.total_themes == 0
        assert data.score_deltas == ()
        assert data.override_action_counts == {}
        assert data.conflict_counts == {}
        assert data.theme_path_counts == {}


# ----------------------- score deltas -----------------------


class TestScoreDeltas:
    def test_override_score_produces_delta(self) -> None:
        emitter = CalibrationEmitter()
        sig = _signal("s-1", composite=0.7)
        rec = _record(
            target_id="s-1",
            action=OverrideAction.OVERRIDE_SCORE,
            payload={"new_composite": 0.3},
        )
        data = emitter.emit(
            cycle_id="c-1",
            overrides=(rec,),
            conflicts=(),
            theme_paths=(),
            signals=(sig,),
        )
        assert len(data.score_deltas) == 1
        d = data.score_deltas[0]
        assert isinstance(d, ScoreDelta)
        assert d.target_id == ID("s-1")
        assert d.original_composite == pytest.approx(0.7)
        assert d.new_composite == pytest.approx(0.3)

    def test_missing_signal_records_none_original(self) -> None:
        """If the Signal is not in the input, original_composite is None."""
        emitter = CalibrationEmitter()
        rec = _record(
            target_id="missing-signal",
            action=OverrideAction.OVERRIDE_SCORE,
            payload={"new_composite": 0.4},
        )
        data = emitter.emit(
            cycle_id="c-1",
            overrides=(rec,),
            conflicts=(),
            theme_paths=(),
            signals=(),
        )
        assert len(data.score_deltas) == 1
        assert data.score_deltas[0].original_composite is None
        assert data.score_deltas[0].new_composite == pytest.approx(0.4)

    def test_non_override_actions_excluded_from_deltas(self) -> None:
        emitter = CalibrationEmitter()
        rec_mark = _record(target_id="s-1", action=OverrideAction.MARK_NOISE)
        rec_change = _record(target_id="s-2", action=OverrideAction.CHANGE_TIER)
        data = emitter.emit(
            cycle_id="c-1",
            overrides=(rec_mark, rec_change),
            conflicts=(),
            theme_paths=(),
        )
        assert data.score_deltas == ()

    def test_malformed_payload_skipped(self) -> None:
        emitter = CalibrationEmitter()
        rec = _record(
            target_id="s-1",
            action=OverrideAction.OVERRIDE_SCORE,
            payload={"new_composite": "not-a-number"},
        )
        data = emitter.emit(
            cycle_id="c-1",
            overrides=(rec,),
            conflicts=(),
            theme_paths=(),
        )
        assert data.score_deltas == ()


# ----------------------- action distribution -----------------------


class TestActionDistribution:
    def test_counts_per_action(self) -> None:
        emitter = CalibrationEmitter()
        records = (
            _record(target_id="t-1", action=OverrideAction.MARK_NOISE),
            _record(target_id="t-2", action=OverrideAction.MARK_NOISE),
            _record(target_id="t-3", action=OverrideAction.CHANGE_TIER),
            _record(target_id="t-4", action=OverrideAction.UPDATE_NOTES,
                    payload={"notes": "n"}),
        )
        data = emitter.emit(
            cycle_id="c-1",
            overrides=records,
            conflicts=(),
            theme_paths=(),
        )
        assert data.override_action_counts == {
            "mark_noise": 2,
            "change_tier": 1,
            "update_notes": 1,
        }


# ----------------------- conflict distribution -----------------------


class TestConflictDistribution:
    def test_counts_per_kind(self) -> None:
        emitter = CalibrationEmitter()
        conflicts = (
            _conflict(ConflictKind.DUPLICATE_OVERRIDE),
            _conflict(ConflictKind.DUPLICATE_OVERRIDE),
            _conflict(ConflictKind.STALE_OVERRIDE),
        )
        data = emitter.emit(
            cycle_id="c-1",
            overrides=(),
            conflicts=conflicts,
            theme_paths=(),
        )
        assert data.conflict_counts == {
            "duplicate_override": 2,
            "stale_override": 1,
        }


# ----------------------- theme-path distribution -----------------------


class TestThemePathDistribution:
    def test_counts_per_path(self) -> None:
        emitter = CalibrationEmitter()
        paths = (
            ThemePath.EVOLVE,
            ThemePath.EVOLVE,
            ThemePath.EVOLVE,
            ThemePath.SUPERSEDE,
            ThemePath.HOLD,
        )
        data = emitter.emit(
            cycle_id="c-1",
            overrides=(),
            conflicts=(),
            theme_paths=paths,
        )
        assert data.theme_path_counts == {
            "evolve": 3,
            "supersede": 1,
            "hold": 1,
        }


# ----------------------- totals -----------------------


class TestTotals:
    def test_totals_match_input_sizes(self) -> None:
        emitter = CalibrationEmitter()
        sigs = (_signal("s-1"), _signal("s-2"), _signal("s-3"))
        records = (
            _record(target_id="t-1", action=OverrideAction.MARK_NOISE),
            _record(target_id="t-2", action=OverrideAction.CHANGE_TIER,
                    payload={"new_tier": "tier_1"}),
        )
        conflicts = (_conflict(ConflictKind.CONFLICTING_OVERRIDE),)
        themes = (object(), object())  # placeholder Theses; count only
        data = emitter.emit(
            cycle_id="c-1",
            overrides=records,
            conflicts=conflicts,
            theme_paths=(),
            signals=sigs,
            themes=themes,
        )
        assert data.total_signals == 3
        assert data.total_overrides == 2
        assert data.total_conflicts == 1
        assert data.total_themes == 2


# ----------------------- serialization -----------------------


class TestSerialization:
    def test_to_dict_is_json_serializable(self) -> None:
        emitter = CalibrationEmitter()
        data = emitter.emit(
            cycle_id="c-1",
            overrides=(),
            conflicts=(_conflict(ConflictKind.DUPLICATE_OVERRIDE),),
            theme_paths=(ThemePath.EVOLVE,),
            signals=(_signal("s-1"),),
        )
        json.dumps(data.to_dict())

    def test_to_json(self) -> None:
        emitter = CalibrationEmitter()
        data = emitter.emit(
            cycle_id="c-1",
            overrides=(),
            conflicts=(),
            theme_paths=(),
        )
        s = data.to_json()
        # Round-trip through json.
        parsed = json.loads(s)
        assert parsed["cycle_id"] == "c-1"


# ----------------------- emit_from_store convenience -----------------------


class TestEmitFromStore:
    def test_reads_overrides_and_signals_from_store(self) -> None:
        store = InMemoryStore()
        sig = _signal("s-1", composite=0.8)
        store.put_signal(sig)
        # Append an override directly to the store.
        rec = _record(
            target_id="s-1",
            action=OverrideAction.OVERRIDE_SCORE,
            payload={"new_composite": 0.2},
        )
        store.append_override(rec)
        emitter = CalibrationEmitter()
        data = emitter.emit_from_store(
            cycle_id="c-1",
            store=store,
        )
        assert data.total_signals == 1
        assert data.total_overrides == 1
        assert data.score_deltas[0].original_composite == pytest.approx(0.8)
        assert data.score_deltas[0].new_composite == pytest.approx(0.2)


# ----------------------- frozen / immutability -----------------------


class TestCalibrationDataFrozen:
    def test_calibration_data_is_frozen(self) -> None:
        d = CalibrationData(
            cycle_id="c-1",
            emitted_at="2026-07-19T00:00:00Z",
            total_signals=0,
            total_overrides=0,
            total_conflicts=0,
            total_themes=0,
            score_deltas=(),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            d.total_signals = 99  # type: ignore[misc]


# ----------------------- dep inversion -----------------------


class TestDepInversion:
    def test_calibration_does_not_import_runtime(self) -> None:
        import re

        import src.research.calibration as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        assert not re.search(r"^\s*from\s+src\.runtime", contents, re.MULTILINE)

    def test_calibration_does_not_import_workflow(self) -> None:
        import re

        import src.research.calibration as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        assert "from src.workflow.gates" not in contents
        assert "from src.workflow.stages" not in contents

    def test_calibration_does_not_import_concrete_store(self) -> None:
        import re

        import src.research.calibration as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        import_re = re.compile(
            r"^\s*(?:from\s+src\.persistence\.in_memory|import\s+src\.persistence\.in_memory)",
            re.MULTILINE,
        )
        assert not import_re.search(contents)


# ----------------------- integration: curator → calibration -----------------------


class TestCuratorToCalibration:
    def test_curator_overrides_feed_calibration(self) -> None:
        """End-to-end: Curator produces overrides → Calibration consumes them."""
        from src.core.entities import Entity, EntityKind
        from src.research.curator import Curator

        store = InMemoryStore()
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        sig = _signal("s-1", composite=0.85)
        store.put_entity(entity)
        store.put_signal(sig)

        curator = Curator(store=store, actor="curator:alice")
        curator.override_score("s-1", new_composite=0.4, rationale="too high")
        curator.mark_noise("s-1", rationale="irrelevant")

        emitter = CalibrationEmitter()
        data = emitter.emit_from_store(
            cycle_id="cycle-xyz",
            store=store,
        )
        # Two overrides recorded.
        assert data.total_overrides == 2
        # Action distribution includes both.
        assert data.override_action_counts.get("override_score") == 1
        assert data.override_action_counts.get("mark_noise") == 1
        # Score delta captures the original → new composite.
        assert data.score_deltas[0].original_composite == pytest.approx(0.85)
        assert data.score_deltas[0].new_composite == pytest.approx(0.4)