"""Sync Health Monitor (component C7, specs/03 §3.2, specs/09 §9.5).

Continuously answers "is the data we are acting on trustworthy?" by tracking, per source:
freshness (age of the last event), throughput (rate), and event count. It rolls these into
a single ``GO / DEGRADED / FAULT`` status with actionable alarms, and can flag the
dangerous case of *racing on a stale position feed* when given the race-state engine.

Health is a first-class feature, not an afterthought: the operator must be able to trust,
at a glance, that injected cars reflect reality before the green flag (specs/09).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .bus import TOPIC_HEALTH, EventBus
from .model import RaceState


class Status(str, Enum):
    GO = "go"
    DEGRADED = "degraded"
    FAULT = "fault"

    def worse_of(self, other: "Status") -> "Status":
        """Return the more severe of this status and ``other``.

        Args:
            other: Status to compare against.

        Returns:
            Whichever status ranks worse (FAULT > DEGRADED > GO).
        """
        order = [Status.GO, Status.DEGRADED, Status.FAULT]
        return self if order.index(self) >= order.index(other) else other


@dataclass
class SourceConfig:
    """Per-source freshness thresholds (seconds) and whether it is safety-critical.

    Defaults suit a high-rate position feed. Sparse feeds (e.g. lap timing, ~90 s apart)
    should be registered with much larger thresholds so they are not perpetually FAULT.

    Attributes:
        fresh: Maximum age (seconds) for GO status.
        fault: Age (seconds) above which the source is FAULT; between ``fresh`` and
            ``fault`` is DEGRADED.
        critical: Whether the source is safety-critical and affects overall status.
    """

    fresh: float = 0.5    # <= fresh -> GO
    fault: float = 2.0    # > fault -> FAULT (between fresh and fault -> DEGRADED)
    critical: bool = True


@dataclass
class SourceHealth:
    """Health summary for a single source.

    Attributes:
        name: Source name.
        count: Number of events observed.
        rate_hz: Observed throughput in events per second.
        age: Seconds since the last event.
        status: Computed status for the source.
    """

    name: str
    count: int
    rate_hz: float
    age: float
    status: Status


@dataclass
class HealthSnapshot:
    """A point-in-time view of overall and per-source health.

    Attributes:
        t: Time the snapshot was taken.
        overall: Worst status across critical sources.
        sources: Per-source health, keyed by source name.
        alarms: Human-readable alarm strings raised by this snapshot.
    """

    t: float
    overall: Status
    sources: dict[str, SourceHealth] = field(default_factory=dict)
    alarms: list[str] = field(default_factory=list)


@dataclass
class _Stat:
    """Running observation stats for a source.

    Attributes:
        count: Number of events observed.
        first_t: Timestamp of the first event, or ``None`` if none seen.
        last_t: Timestamp of the most recent event, or ``None`` if none seen.
    """

    count: int = 0
    first_t: Optional[float] = None
    last_t: Optional[float] = None


class HealthMonitor:
    def __init__(self, bus: Optional[EventBus] = None, state_engine=None,
                 default: Optional[SourceConfig] = None):
        self.bus = bus
        self.state_engine = state_engine
        self._default = default or SourceConfig()
        self._cfg: dict[str, SourceConfig] = {}
        self._stat: dict[str, _Stat] = {}

    def register(self, name: str, fresh: float = 0.5, fault: float = 2.0,
                 critical: bool = True) -> None:
        """Configure thresholds for a source (call before/while observing it).

        Args:
            name: Source name to configure.
            fresh: Maximum age (seconds) for GO status.
            fault: Age (seconds) above which the source is FAULT.
            critical: Whether the source is safety-critical.
        """
        self._cfg[name] = SourceConfig(fresh=fresh, fault=fault, critical=critical)

    def observe(self, source_name: str, event, now: float) -> None:
        """Record an observed event for a source.

        Args:
            source_name: Source the event came from.
            event: The observed event; its ``t`` updates freshness stats.
            now: Current time (unused for stat tracking but kept for the interface).
        """
        st = self._stat.setdefault(source_name, _Stat())
        st.count += 1
        if st.first_t is None:
            st.first_t = event.t
        st.last_t = event.t

    # -- evaluation --------------------------------------------------------- #

    def _config(self, name: str) -> SourceConfig:
        return self._cfg.get(name, self._default)

    def snapshot(self, now: float) -> HealthSnapshot:
        """Compute the current health snapshot across all observed sources.

        Args:
            now: Current time used to compute source ages.

        Returns:
            A ``HealthSnapshot`` with per-source health, overall status, and alarms,
            including a stale-data alarm if the field is racing on a faulted feed.
        """
        sources: dict[str, SourceHealth] = {}
        overall = Status.GO
        alarms: list[str] = []

        for name, st in self._stat.items():
            cfg = self._config(name)
            age = now - st.last_t if st.last_t is not None else float("inf")
            span = ((st.last_t - st.first_t)
                    if (st.last_t is not None and st.first_t is not None) else 0.0)
            rate = (st.count - 1) / span if span > 0 else 0.0

            if age <= cfg.fresh:
                status = Status.GO
            elif age <= cfg.fault:
                status = Status.DEGRADED
            else:
                status = Status.FAULT

            sources[name] = SourceHealth(name, st.count, rate, age, status)
            if cfg.critical:
                overall = overall.worse_of(status)
            if status != Status.GO and cfg.critical:
                alarms.append(f"{name}: {status.value} (age {age:.2f}s)")

        # Dangerous case: the field is racing/neutralised but a critical feed is stale.
        if self.state_engine is not None:
            racing = self.state_engine.state in (RaceState.GREEN, RaceState.NEUTRALISED)
            if racing and overall == Status.FAULT:
                alarms.append("RACING ON STALE POSITION DATA — injection unreliable")

        return HealthSnapshot(t=now, overall=overall, sources=sources, alarms=alarms)

    def tick(self, now: float) -> HealthSnapshot:
        """Compute a snapshot and publish it on the bus.

        Args:
            now: Current time used to compute source ages.

        Returns:
            The computed ``HealthSnapshot`` (also published if a bus is configured).
        """
        snap = self.snapshot(now)
        if self.bus is not None:
            self.bus.publish(TOPIC_HEALTH, snap)
        return snap
