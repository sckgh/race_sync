"""The shared Race State Engine (specs/06-race-state-sync.md).

Single source of truth for the state shared between the real and virtual fields:
PRE_RACE -> FORMATION -> GREEN <-> NEUTRALISED (Safety Car / Code 60) -> CHEQUERED.

Design choices that match the spec and the agreed decisions:

* **Operator-driven** GREEN and Code 60 (manual trigger), with guarded transitions.
* **Timed finish** armed by authoritative ``RACE_COMPLETED`` timing, then confirmed by
  the operator firing the chequer (human-in-the-loop in v1).
* Every transition is emitted on the bus and appended to an **audit log** with source
  and timestamp; nothing here mutates official real-race timing.
* **Skews** (virtual-vs-real start, and time spent neutralised) are recorded so Scoring
  can judge fairness of the timed finish.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .bus import TOPIC_STATE, EventBus
from .model import RaceState, StateTransition, TimingEvent, TimingEventKind


class InvalidTransition(RuntimeError):
    """Raised when an operator/timing action is not legal from the current state."""


# Legal transitions (specs/06 §6.1). CHEQUERED is terminal.
_ALLOWED: dict[RaceState, set[RaceState]] = {
    RaceState.PRE_RACE: {RaceState.FORMATION},
    RaceState.FORMATION: {RaceState.GREEN},
    RaceState.GREEN: {RaceState.NEUTRALISED, RaceState.CHEQUERED},
    RaceState.NEUTRALISED: {RaceState.GREEN, RaceState.CHEQUERED},
    RaceState.CHEQUERED: set(),
}


@dataclass
class _Neutralisation:
    start_t: float
    end_t: Optional[float] = None


class RaceStateEngine:
    def __init__(self, bus: Optional[EventBus] = None, clock=None):
        self.bus = bus
        self._clock = clock  # callable -> float; tests pass explicit t instead
        self.state = RaceState.PRE_RACE
        self.audit: list[StateTransition] = []

        # Race facts tracked for fairness/scoring.
        self.green_t: Optional[float] = None          # when the (real) race went green
        self.leader_car: Optional[str] = None
        self.leader_lap: int = 0
        self.finish_armed: bool = False
        self.finish_t: Optional[float] = None         # real leader completed distance
        self.chequered_t: Optional[float] = None
        self._neutralisations: list[_Neutralisation] = []

    # -- helpers ------------------------------------------------------------ #

    def _now(self, t: Optional[float]) -> float:
        if t is not None:
            return t
        if self._clock is not None:
            return self._clock()
        raise ValueError("no timestamp supplied and no clock configured")

    def _transition(self, to: RaceState, t: float, source: str, reason: str, **meta) -> None:
        if to not in _ALLOWED[self.state]:
            raise InvalidTransition(f"{self.state.value} -> {to.value} is not allowed")
        tr = StateTransition(self.state, to, t, source, reason, meta)
        self.state = to
        self.audit.append(tr)
        if self.bus is not None:
            self.bus.publish(TOPIC_STATE, tr)

    # -- operator actions (specs/06 §6.2–6.4) ------------------------------ #

    def arm(self, t: Optional[float] = None) -> None:
        """PRE_RACE -> FORMATION: virtual field forms up, held until green."""
        self._transition(RaceState.FORMATION, self._now(t), "operator", "arm formation")

    def go_green(self, t: Optional[float] = None, real_start: bool = True) -> None:
        """Release the field (start) or restart after a neutralisation."""
        now = self._now(t)
        restart = self.state == RaceState.NEUTRALISED
        if restart and self._neutralisations and self._neutralisations[-1].end_t is None:
            self._neutralisations[-1].end_t = now
        self._transition(RaceState.GREEN, now, "operator",
                         "restart" if restart else "green", restart=restart)
        if not restart:
            self.green_t = now

    def set_code60(self, on: bool, t: Optional[float] = None, reason: str = "") -> None:
        """Deploy (Safety Car -> Code 60) or withdraw it.

        ``on`` from GREEN neutralises the field; ``off`` restarts (equivalent to
        ``go_green`` from NEUTRALISED). Laps keep counting throughout (specs/06 §6.3).
        """
        now = self._now(t)
        if on:
            self._transition(RaceState.NEUTRALISED, now, "operator",
                             reason or "safety car -> code 60")
            self._neutralisations.append(_Neutralisation(start_t=now))
        else:
            self.go_green(now)

    def arm_finish(self, t: Optional[float] = None, car_id: Optional[str] = None) -> None:
        """Mark that the real leader has completed the distance; chequer can now fire."""
        self.finish_armed = True
        self.finish_t = self._now(t)
        if car_id is not None:
            self.leader_car = car_id

    def fire_chequer(self, t: Optional[float] = None, force: bool = False) -> None:
        """Throw the (timed) chequered flag for the virtual field.

        Requires the finish to be armed by authoritative timing unless ``force`` (an
        explicit operator override, recorded as such in the audit log).
        """
        if not self.finish_armed and not force:
            raise InvalidTransition("finish not armed (real leader has not completed distance)")
        now = self._now(t)
        # If we are neutralised at the finish, the chequer still falls (specs/06 §6.3).
        if self._neutralisations and self._neutralisations[-1].end_t is None:
            self._neutralisations[-1].end_t = now
        self._transition(RaceState.CHEQUERED, now, "operator",
                         "timed finish" + (" (forced)" if force else ""),
                         forced=force)
        self.chequered_t = now

    # -- timing inputs (specs/06 §6.4) ------------------------------------- #

    def on_timing_event(self, ev: TimingEvent) -> None:
        """React to authoritative timing: track leader, arm the timed finish."""
        if ev.kind == TimingEventKind.LEADER_CHANGED:
            self.leader_car = ev.car_id
            if ev.lap is not None:
                self.leader_lap = ev.lap
        elif ev.kind == TimingEventKind.LAP_COMPLETED and ev.car_id == self.leader_car:
            if ev.lap is not None:
                self.leader_lap = ev.lap
        elif ev.kind == TimingEventKind.RACE_COMPLETED:
            self.arm_finish(ev.t, ev.car_id)

    # -- derived facts ------------------------------------------------------ #

    @property
    def is_code60(self) -> bool:
        return self.state == RaceState.NEUTRALISED

    def neutralised_seconds(self) -> float:
        """Total time spent neutralised (closed intervals), for fairness review."""
        total = 0.0
        for n in self._neutralisations:
            if n.end_t is not None:
                total += n.end_t - n.start_t
        return total

    def start_skew(self, virtual_green_t: float) -> Optional[float]:
        """Signed seconds the virtual field went green after the real field (specs/06)."""
        if self.green_t is None:
            return None
        return virtual_green_t - self.green_t
