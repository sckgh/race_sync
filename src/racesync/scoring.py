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
    """A registered competitor.

    Attributes:
        car_id: Unique identifier for the car.
        number: Competitor's race number.
        klass: Whether the entry is a real or virtual car.
        driver: Driver name.
        division: Division (A-E); applies to the real class only.
    """

    car_id: str
    number: str
    klass: CarClass
    driver: str = ""
    division: Optional[str] = None


@dataclass
class Penalty:
    """A penalty applied to a car.

    Attributes:
        laps: Lap penalty.
        seconds: Time penalty in seconds.
        reason: Description of why the penalty was issued.
    """

    laps: int = 0
    seconds: float = 0.0
    reason: str = ""


@dataclass
class CarScore:
    """Accumulated scoring state for a single car.

    Attributes:
        entry: The registered competitor this score belongs to.
        laps: Authoritative laps completed.
        last_lap: Most recent lap time.
        best_lap: Best lap time so far.
        s: Latest along-track fraction.
        pos_total: Latest position progress (lap + s).
        source: Data-quality indicator for the latest position.
        quality: Confidence in the latest position.
        penalties: Penalties applied to the car.
    """

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
    """A car's position within a class classification.

    Attributes:
        rank: Position within the class (1 is the leader).
        score: The car's accumulated score.
        gap_laps: Progress gap to the class leader, in laps.
    """

    rank: int
    score: CarScore
    gap_laps: float  # progress gap to the class leader, in laps (float)


@dataclass
class Classification:
    """Ordered standings for a single class.

    Attributes:
        klass: The class being classified.
        standings: Ordered standings, most-advanced first.
        finished: Whether this is a frozen timed-finish result.
        at_t: Time the classification represents.
        fairness: Fairness inputs recorded alongside the result.
    """

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
        """Register a competitor so its score is tracked.

        Args:
            entry: The competitor to register.
        """
        self._scores[entry.car_id] = CarScore(entry=entry)

    def entries(self) -> list[Entry]:
        """Return all registered competitors."""
        return [s.entry for s in self._scores.values()]

    # -- bus wiring (specs/03) --------------------------------------------- #

    def attach(self, bus: EventBus) -> None:
        """Subscribe to position and timing streams so scoring updates live.

        Args:
            bus: Event bus carrying the timing and position topics.
        """
        bus.subscribe(TOPIC_TIMING, self.on_timing_event)
        bus.subscribe(TOPIC_POSITION, self.on_position)

    # -- ingestion ---------------------------------------------------------- #

    def on_timing_event(self, ev: TimingEvent) -> None:
        """Update a car's laps and lap times from an authoritative timing event.

        Args:
            ev: Timing event; ignored unless it names a registered car.
        """
        if ev.car_id is None or ev.car_id not in self._scores:
            return
        sc = self._scores[ev.car_id]
        if ev.kind == TimingEventKind.LAP_COMPLETED and ev.lap is not None:
            sc.laps = max(sc.laps, ev.lap)
            if ev.value is not None:
                sc.last_lap = ev.value
                sc.best_lap = ev.value if sc.best_lap is None else min(sc.best_lap, ev.value)

    def on_position(self, est: PositionEstimate) -> None:
        """Update a car's latest track position from a position estimate.

        Args:
            est: Position estimate; ignored unless it names a registered car.
        """
        sc = self._scores.get(est.car_id)
        if sc is None:
            return
        sc.s = est.lap_distance.s
        sc.pos_total = est.lap_distance.total
        sc.source = est.source
        sc.quality = est.quality

    def add_penalty(self, car_id: str, laps: int = 0, seconds: float = 0.0,
                    reason: str = "") -> None:
        """Apply a penalty to a registered car.

        Args:
            car_id: Car to penalise; ignored if not registered.
            laps: Lap penalty to apply.
            seconds: Time penalty in seconds.
            reason: Description of the penalty.
        """
        if car_id in self._scores:
            self._scores[car_id].penalties.append(Penalty(laps, seconds, reason))

    # -- classification ----------------------------------------------------- #

    def classify(self, klass: CarClass, at_t: Optional[float] = None) -> Classification:
        """Return the current standings within a class (most-advanced first).

        If the race is already finalized, returns the frozen timed-finish result.

        Args:
            klass: Class to classify.
            at_t: Time the classification represents, if known.

        Returns:
            The class ``Classification``.
        """
        if self._final is not None:
            return self._final[klass]
        scores = [s for s in self._scores.values() if s.entry.klass == klass]
        return self._build(klass, scores, finished=False, at_t=at_t)

    def combined(self, at_t: Optional[float] = None) -> dict[CarClass, Classification]:
        """Return classifications for every class, keyed by class.

        Args:
            at_t: Time the classifications represent, if known.

        Returns:
            A mapping from each ``CarClass`` to its ``Classification``.
        """
        return {k: self.classify(k, at_t) for k in CarClass}

    def finalize(self, t: float) -> dict[CarClass, Classification]:
        """Freeze the timed-finish classification.

        Call at CHEQUERED (specs/08 §8.3).

        Args:
            t: Time of the chequered flag.

        Returns:
            A mapping from each ``CarClass`` to its frozen ``Classification``.
        """
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
        """Build a class classification by ranking the given scores.

        Args:
            klass: Class being built.
            scores: Car scores to rank.
            finished: Whether the result is a frozen timed finish.
            at_t: Time the classification represents.
            fairness: Fairness inputs to attach, if any.

        Returns:
            The assembled ``Classification`` with ranks and gaps filled in.
        """
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
        """Pull fairness inputs from the state engine for the result record.

        Args:
            t: Time of the finish.

        Returns:
            A dict of fairness facts, or empty if no state engine is configured.
        """
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
    """Render a class classification as a compact text table.

    Args:
        c: Classification to render.

    Returns:
        The formatted multi-line table as a string.
    """
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
