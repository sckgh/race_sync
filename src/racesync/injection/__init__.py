"""Live car injection (component C3) — the make-or-break capability (specs/05).

This package is the Phase-1 feasibility-spike scaffolding: a platform-agnostic
``SimInjectionAdapter`` boundary, a deterministic in-memory adapter for testing the rig
without a simulator, an Assetto Corsa target stub, and a latency-measurement harness that
scores a run against the specs/09 targets.

Nothing here claims injection *works* on a given platform — that is exactly what the spike
must determine. The harness exists to measure it.
"""

from .base import (
    GlobalSimState,
    LoopbackAdapter,
    PhantomState,
    SimInjectionAdapter,
)
from .harness import (
    InjectionHarness,
    LatencyStats,
    LatencyTargets,
    SpikeReport,
    Verdict,
)
from .receiver import PhantomReceiver

__all__ = [
    "PhantomState",
    "GlobalSimState",
    "SimInjectionAdapter",
    "LoopbackAdapter",
    "InjectionHarness",
    "LatencyStats",
    "LatencyTargets",
    "SpikeReport",
    "Verdict",
    "PhantomReceiver",
]
