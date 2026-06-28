"""Injection latency-measurement harness (specs/05 §5.4, scored vs specs/09 §9.1).

The spike's whole purpose is to answer, with evidence: *can we inject moving cars at
acceptable fidelity and latency?* This harness drives position estimates through a
``SimInjectionAdapter`` and measures **end-to-end injection latency** — from a position's
capture time to the moment its phantom state is applied — then scores the run against the
targets (typical ≤250 ms, degraded >500 ms).

Two modes:

* **Live** (real spike): construct with ``clock=time.monotonic``; feed estimates that
  carry real capture timestamps; latency = ``clock() - est.t``.
* **Simulation** (no sim / offline): pass an explicit ``apply_latency`` per sample (e.g. a
  modelled transport+apply delay), so the reporting machinery can be exercised and tested
  deterministically.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable, Optional

from .base import PhantomState, SimInjectionAdapter


class Verdict(str, Enum):
    PASS = "pass"
    MARGINAL = "marginal"
    FAIL = "fail"


@dataclass(frozen=True)
class LatencyTargets:
    """Latency thresholds in seconds (specs/09 §9.1)."""

    typical: float = 0.25     # p50 should be at/under this
    degraded: float = 0.50    # p95 over this = degraded/fail


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Linear-interpolated percentile (pct in [0, 100]) of a sorted list."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = rank - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


@dataclass
class LatencyStats:
    n: int = 0
    min: float = 0.0
    p50: float = 0.0
    p95: float = 0.0
    max: float = 0.0
    mean: float = 0.0

    @classmethod
    def from_samples(cls, samples: list[float]) -> "LatencyStats":
        if not samples:
            return cls()
        s = sorted(samples)
        return cls(
            n=len(s), min=s[0], max=s[-1],
            p50=_percentile(s, 50), p95=_percentile(s, 95),
            mean=sum(s) / len(s),
        )


@dataclass
class SpikeReport:
    stats: LatencyStats
    targets: LatencyTargets
    verdict: Verdict
    notes: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        s, t = self.stats, self.targets
        ms = lambda v: f"{v * 1000:.0f}ms"
        lines = [
            f"injection spike: {self.verdict.value.upper()}  (n={s.n})",
            f"  latency  p50={ms(s.p50)}  p95={ms(s.p95)}  "
            f"min={ms(s.min)}  max={ms(s.max)}  mean={ms(s.mean)}",
            f"  targets  typical(p50)<= {ms(t.typical)}  degraded(p95)<= {ms(t.degraded)}",
        ]
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def score(stats: LatencyStats, targets: LatencyTargets) -> Verdict:
    if stats.n == 0:
        return Verdict.FAIL
    if stats.p50 <= targets.typical and stats.p95 <= targets.degraded:
        return Verdict.PASS
    if stats.p50 <= targets.degraded:
        return Verdict.MARGINAL
    return Verdict.FAIL


class InjectionHarness:
    """Drives phantom states into an adapter and measures injection latency."""

    def __init__(self, adapter: SimInjectionAdapter,
                 clock: Callable[[], float] = time.monotonic,
                 targets: Optional[LatencyTargets] = None):
        self.adapter = adapter
        self._clock = clock
        self.targets = targets or LatencyTargets()
        self.samples: list[float] = []
        self.notes: list[str] = []

    def inject(self, est, apply_latency: Optional[float] = None) -> float:
        """Inject one estimate's phantom state; return the measured latency sample.

        If ``apply_latency`` is given (simulation mode), it is used directly; otherwise
        latency is ``clock() - est.t`` measured right after the adapter applies (live mode).
        """
        state = PhantomState.from_estimate(est)
        self.adapter.apply(state)
        lat = apply_latency if apply_latency is not None else (self._clock() - est.t)
        if lat < 0:
            lat = 0.0
            self.notes.append(f"clock skew: negative latency clamped for {est.car_id}")
        self.samples.append(lat)
        return lat

    def run(self, estimates: Iterable,
            latency_model: Optional[Callable[[int, object], float]] = None) -> SpikeReport:
        """Inject a sequence of estimates. ``latency_model(i, est) -> seconds`` (optional)
        supplies a modelled latency per sample for offline simulation runs."""
        for i, est in enumerate(estimates):
            self.inject(est, apply_latency=(latency_model(i, est) if latency_model else None))
        return self.report()

    def report(self) -> SpikeReport:
        stats = LatencyStats.from_samples(self.samples)
        verdict = score(stats, self.targets)
        notes = list(self.notes)
        if stats.n == 0:
            notes.append("no samples — adapter received no phantom states")
        return SpikeReport(stats=stats, targets=self.targets, verdict=verdict, notes=notes)
