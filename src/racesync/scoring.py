"""Scoring & Classification (component C6, specs/08-scoring-and-classification.md).

Produces one combined result for the hybrid race with **real and virtual cars scored as
separate classes**. Principles enforced here:

* Real-field laps/order come from authoritative timing (``LAP_COMPLETED`` events); virtual
  cars flow through the same channels (the Sim Telemetry Reader will emit equivalent
  events) and are classified by their registered class — Scoring is source-agnostic.
* The finish is **timed** (specs/08 §8.3): at the chequer we rank on laps completed + track
  position at that instant. ``finalize`` snapshots exactly that.
* Penalties (official real-field, or virtual-class Code 60 enforcement) are applied to the
  ranking and **annotated**, never hidden.
* Fairness inputs (start-skew, neutralised time) are recorded alongside the result for
  officials to review — Scoring flags, officials adjudicate.

This module classifies; it does not invent timing. Where it shows a between-loops position
that is an *estimate* (from the Position Model), the data-quality indicator says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .bus import TOPIC_POSITION, TOPIC_TIMING, EventBus
from .model import (
    PositionEstimate,
    PositionSourceKind,
    TimingEvent,
    TimingEventKind,
)


class CarClass(str, Enum):
    REAL = "real"
    VIRTUAL = "virtual"


@dataclass(frozen=True)
class Entry:
    """A registered competitor. ``division`` (A–E) applies to the real class only."""

    car_id: str
    number: str
    klass: CarClass
    driver: str = ""
    division: Optional[str] = None


@dataclass
class Penalty:
    laps: int = 0
    seconds: float = 0.0
    reason: str = ""


@dataclass
class CarScore:
    entry: Entry
    laps: int = 0                       # authoritative laps completed
    last_lap: Optional[float] = None
    best_lap: Optional[float] = None
    s: float = 0.0                      # latest along-track fraction
    pos_total: float = 0.0             # latest position progress (lap + s)
    source: Optional[PositionSourceKind] = None  # data-quality indicator
    quality: float = 1.0
    penalties: list[Penalty] = field(default_factory=list)

    @property
    def lap_penalty(self) -> int:
        return sum(p.laps for p in self.penalties)

    @property
    def time_penalty(self) -> float:
        return sum(p.seconds for p in self.penalties)

    @property
    def progress(self) -> float:
        """Live progress for ordering: authoritative laps + fraction, or position."""
        return max(self.laps + self.s, self.pos_total)

    @property
    def effective_progress(self) -> float:
        """Progress after lap penalties (used for classification order)."""
        return self.progress - self.lap_penalty


@dataclass
class Standing:
    rank: int
    score: CarScore
    gap_laps: float  # progress gap to the class leader, in laps (float)


@dataclass
class Classification:
    klass: CarClass
    standings: list[Standing]
    finished: bool = False
    at_t: Optional[float] = None
    fairness: dict = field(default_factory=dict)


class ScoringService:
    """Tracks per-car scores and produces per-class / combined classifications."""

    def __init__(self, state_engine=None):
        self.state_engine = state_engine
        self._scores: dict[str, CarScore] = {}
        self._final: Optional[dict[CarClass, Classification]] = None

    # -- registration ------------------------------------------------------- #

    def register(self, entry: Entry) -> None:
        self._scores[entry.car_id] = CarScore(entry=entry)

    def entries(self) -> list[Entry]:
        return [s.entry for s in self._scores.values()]

    # -- bus wiring (specs/03) --------------------------------------------- #

    def attach(self, bus: EventBus) -> None:
        """Subscribe to position and timing streams so scoring updates live."""
        bus.subscribe(TOPIC_TIMING, self.on_timing_event)
        bus.subscribe(TOPIC_POSITION, self.on_position)

    # -- ingestion ---------------------------------------------------------- #

    def on_timing_event(self, ev: TimingEvent) -> None:
        if ev.car_id is None or ev.car_id not in self._scores:
            return
        sc = self._scores[ev.car_id]
        if ev.kind == TimingEventKind.LAP_COMPLETED and ev.lap is not None:
            sc.laps = max(sc.laps, ev.lap)
            if ev.value is not None:
                sc.last_lap = ev.value
                sc.best_lap = ev.value if sc.best_lap is None else min(sc.best_lap, ev.value)

    def on_position(self, est: PositionEstimate) -> None:
        sc = self._scores.get(est.car_id)
        if sc is None:
            return
        sc.s = est.lap_distance.s
        sc.pos_total = est.lap_distance.total
        sc.source = est.source
        sc.quality = est.quality

    def add_penalty(self, car_id: str, laps: int = 0, seconds: float = 0.0,
                    reason: str = "") -> None:
        if car_id in self._scores:
            self._scores[car_id].penalties.append(Penalty(laps, seconds, reason))

    # -- classification ----------------------------------------------------- #

    def classify(self, klass: CarClass, at_t: Optional[float] = None) -> Classification:
        """Current standings within a class (most-advanced first).

        If the race is already finalized, returns the frozen timed-finish result.
        """
        if self._final is not None:
            return self._final[klass]
        scores = [s for s in self._scores.values() if s.entry.klass == klass]
        return self._build(klass, scores, finished=False, at_t=at_t)

    def combined(self, at_t: Optional[float] = None) -> dict[CarClass, Classification]:
        return {k: self.classify(k, at_t) for k in CarClass}

    def finalize(self, t: float) -> dict[CarClass, Classification]:
        """Freeze the timed-finish classification (call at CHEQUERED, specs/08 §8.3)."""
        fairness = self._fairness(t)
        result: dict[CarClass, Classification] = {}
        for klass in CarClass:
            scores = [s for s in self._scores.values() if s.entry.klass == klass]
            result[klass] = self._build(klass, scores, finished=True, at_t=t,
                                         fairness=fairness)
        self._final = result
        return result

    # -- internals ---------------------------------------------------------- #

    def _build(self, klass, scores, finished, at_t, fairness=None) -> Classification:
        ordered = sorted(
            scores,
            key=lambda s: (s.effective_progress, -s.time_penalty),
            reverse=True,
        )
        standings: list[Standing] = []
        leader_progress = ordered[0].effective_progress if ordered else 0.0
        for i, sc in enumerate(ordered):
            standings.append(Standing(
                rank=i + 1, score=sc,
                gap_laps=round(leader_progress - sc.effective_progress, 4),
            ))
        return Classification(klass=klass, standings=standings, finished=finished,
                              at_t=at_t, fairness=fairness or {})

    def _fairness(self, t: float) -> dict:
        """Pull fairness inputs from the state engine for the result record."""
        if self.state_engine is None:
            return {}
        return {
            "real_green_t": self.state_engine.green_t,
            "neutralised_seconds": self.state_engine.neutralised_seconds(),
            "finish_t": getattr(self.state_engine, "finish_t", None),
            "chequered_t": getattr(self.state_engine, "chequered_t", None),
        }


# --------------------------------------------------------------------------- #
# Presentation helper (operator/combined view, specs/08 §8.4)
# --------------------------------------------------------------------------- #

def format_classification(c: Classification) -> str:
    """Render a class classification as a compact text table."""
    lines = [f"== {c.klass.value.upper()} class "
             f"{'(FINAL, timed finish)' if c.finished else '(live)'} =="]
    header = f"{'P':>2}  {'No':>3}  {'Driver':<14} {'Div':>3}  {'Laps':>4}  " \
             f"{'Gap':>7}  {'Best':>8}  {'Data':>13}"
    lines.append(header)
    for st in c.standings:
        sc = st.score
        e = sc.entry
        gap = "leader" if st.rank == 1 else f"-{st.gap_laps:g}L"
        best = f"{sc.best_lap:.3f}" if sc.best_lap is not None else "-"
        data = sc.source.value if sc.source else "-"
        pen = f" *{sc.lap_penalty}L" if sc.lap_penalty else ""
        lines.append(f"{st.rank:>2}  {e.number:>3}  {e.driver[:14]:<14} "
                     f"{(e.division or '-'):>3}  {sc.laps:>4}  {gap:>7}  "
                     f"{best:>8}  {data:>13}{pen}")
    if c.fairness:
        lines.append(f"   fairness: {c.fairness}")
    return "\n".join(lines)
