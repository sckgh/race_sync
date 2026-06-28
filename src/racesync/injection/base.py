"""The SimInjectionAdapter boundary and the phantom-state it carries (specs/05 §5.6).

A *phantom* is the sim-side representation of a real car, whose world position RaceSync
authors from live data. Every platform integration implements ``SimInjectionAdapter`` so
the rest of the system depends only on this contract — the platform decision (Assetto
Corsa, rFactor 2, …) can change without touching ingestion, fusion, state, or scoring
(specs/03 interface isolation; specs/05 F-05-1).

The ``LoopbackAdapter`` here is a real, dependency-free implementation used to test the
harness and the data path deterministically, with no simulator installed.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class PhantomState:
    """One car's world state to author into the sim, derived from a PositionEstimate.

    Coordinates are in the track plane (metres); an adapter maps them to its sim's
    coordinate system.

    Attributes:
        car_id: Identifier of the real car this phantom represents.
        t: Capture time of the underlying position on the aligned clock; the harness uses
            it to measure end-to-end injection latency.
        x: Track-plane X coordinate in metres.
        y: Track-plane Y coordinate in metres.
        heading: Heading in radians.
        speed: Speed in m/s, or None if unknown.
        quality: Confidence in 0..1; low quality may lead an adapter to ghost/grey the
            phantom.
    """

    car_id: str
    t: float
    x: float
    y: float
    heading: float            # radians
    speed: Optional[float] = None  # m/s
    quality: float = 1.0      # 0..1; low quality -> adapter may ghost/grey the phantom

    @classmethod
    def from_estimate(cls, est) -> "PhantomState":
        """Build a phantom state from a position estimate.

        Args:
            est: A position estimate carrying car_id, t, x, y, heading, speed and quality;
                a missing heading defaults to 0.0.

        Returns:
            A new PhantomState mirroring the estimate.
        """
        return cls(
            car_id=est.car_id, t=est.t, x=est.x, y=est.y,
            heading=(est.heading if est.heading is not None else 0.0),
            speed=est.speed, quality=est.quality,
        )


@dataclass(frozen=True)
class GlobalSimState:
    """Field-wide state imposed on the human virtual field (specs/06).

    Attributes:
        code60: Whether the virtual field is under Code 60.
        chequered: Whether the timed finish has fallen.
    """

    code60: bool = False
    chequered: bool = False


class SimInjectionAdapter(abc.ABC):
    """Contract for pushing phantom cars + global state into a simulator."""

    name: str = "abstract"

    @abc.abstractmethod
    def connect(self) -> None: ...

    @abc.abstractmethod
    def close(self) -> None: ...

    @abc.abstractmethod
    def spawn(self, car_id: str) -> None:
        """Register/allocate a phantom entity before applying states.

        Args:
            car_id: Identifier of the car to allocate a phantom for.
        """

    @abc.abstractmethod
    def apply(self, state: PhantomState) -> None:
        """Author one phantom's world state for the current tick.

        Args:
            state: The phantom state to apply.
        """

    def set_global_state(self, state: GlobalSimState) -> None:
        """Impose field-wide state (e.g. Code 60) on a best-effort, platform-dependent basis.

        Default is a no-op so adapters that cannot enforce it still satisfy the contract;
        a platform that *cannot* impose Code 60 is disqualified for injection (specs/05
        F-05-5), which the spike must record.

        Args:
            state: The field-wide state to impose.
        """

    def health(self) -> dict:
        return {"name": self.name}


class LoopbackAdapter(SimInjectionAdapter):
    """In-memory adapter: records everything applied. For tests and the harness.

    Lets the full inject path be exercised and asserted without a simulator. It also makes
    the harness's latency measurement testable: applies are effectively instant, so any
    measured latency comes from the (injected) clock, not hidden work.
    """

    name = "loopback"

    def __init__(self) -> None:
        self.connected = False
        self.spawned: set[str] = set()
        self.applied: list[PhantomState] = []
        self.global_state = GlobalSimState()
        self.apply_count = 0

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def spawn(self, car_id: str) -> None:
        self.spawned.add(car_id)

    def apply(self, state: PhantomState) -> None:
        if not self.connected:
            raise RuntimeError("adapter not connected")
        if state.car_id not in self.spawned:
            # Auto-spawn on first sight: convenient, and mirrors a real adapter creating
            # the phantom lazily when a car first appears.
            self.spawned.add(state.car_id)
        self.applied.append(state)
        self.apply_count += 1

    def set_global_state(self, state: GlobalSimState) -> None:
        self.global_state = state

    def latest(self, car_id: str) -> Optional[PhantomState]:
        for st in reversed(self.applied):
            if st.car_id == car_id:
                return st
        return None
