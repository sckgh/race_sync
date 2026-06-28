"""Pipeline: wire sources -> fusion -> state engine -> bus (specs/03).

This is the orchestration glue that the CLI previously did inline. It pulls a
**timestamp-ordered** merge across any number of sources (so a GPS feed and a timing feed
interleave correctly), runs each event through fusion and the state engine, optionally
records the raw inputs (for replay parity) and feeds the health monitor, and publishes the
unified ``position.update`` / ``timing.event`` streams on the bus.

Keeping this in one place means every entry point — dev CLI, tests, and the eventual
operator runtime — drives the components identically.
"""

from __future__ import annotations

import heapq
import itertools
from typing import Iterable, Iterator, Optional

from .bus import TOPIC_POSITION, TOPIC_TIMING, EventBus
from .fusion import Fusion
from .model import PositionEstimate, TimingEvent
from .sources.base import RawFix


def merge_streams(sources) -> Iterator[tuple[str, RawFix | TimingEvent]]:
    """Merge multiple sources into one stream ordered by event timestamp.

    Sources may be finite (replay) or unbounded (live); a finite source simply drops out
    of the merge when exhausted. Ordering is a stable k-way merge on ``event.t`` with an
    insertion counter as tie-breaker (so events with equal timestamps keep arrival order
    and we never compare event objects).

    Args:
        sources: Iterable of source objects exposing ``stream()`` and an optional ``name``.

    Yields:
        ``(source_name, event)`` tuples in non-decreasing timestamp order.
    """
    counter = itertools.count()
    heap: list = []
    iters: dict[int, Iterator] = {}
    names: dict[int, str] = {}
    for idx, src in enumerate(sources):
        it = iter(src.stream())
        iters[idx] = it
        names[idx] = getattr(src, "name", f"src{idx}")
        try:
            ev = next(it)
        except StopIteration:
            continue
        heapq.heappush(heap, (ev.t, next(counter), idx, ev))

    while heap:
        _, _, idx, ev = heapq.heappop(heap)
        yield names[idx], ev
        try:
            nxt = next(iters[idx])
        except StopIteration:
            continue
        heapq.heappush(heap, (nxt.t, next(counter), idx, nxt))


class Pipeline:
    """Drives fusion + state engine from a merged source stream.

    Attributes:
        fusion: Fusion component that turns raw fixes into position estimates.
        state_engine: Optional race-state engine fed timing events.
        bus: Optional event bus the produced estimates/events are published on.
        recorder: Optional recorder capturing raw inputs for replay parity.
        health: Optional health monitor observing source liveness.
        logical_now: Latest event timestamp seen so far.
        counts: Running tally of processed ``fix`` and ``timing`` events.
    """

    def __init__(self, fusion: Fusion, state_engine=None, bus: Optional[EventBus] = None,
                 recorder=None, health=None):
        self.fusion = fusion
        self.state_engine = state_engine
        self.bus = bus
        self.recorder = recorder
        self.health = health
        self.logical_now: float = 0.0
        self.counts = {"fix": 0, "timing": 0}

    def feed(self, event: RawFix | TimingEvent, source_name: str = "?"):
        """Process one event end to end.

        Args:
            event: The raw fix or timing event to process.
            source_name: Name of the source the event came from.

        Returns:
            The produced position estimate (for a fix) or the timing event (for timing).

        Raises:
            TypeError: If the event is neither a ``RawFix`` nor a ``TimingEvent``.
        """
        self.logical_now = max(self.logical_now, event.t)
        if self.recorder is not None:
            self.recorder.record(event)
        if self.health is not None:
            self.health.observe(source_name, event, self.logical_now)

        if isinstance(event, RawFix):
            est: PositionEstimate = self.fusion.on_fix(event)
            self.counts["fix"] += 1
            if self.bus is not None:
                self.bus.publish(TOPIC_POSITION, est)
            return est
        if isinstance(event, TimingEvent):
            self.fusion.on_timing_event(event)
            if self.state_engine is not None:
                self.state_engine.on_timing_event(event)
            self.counts["timing"] += 1
            if self.bus is not None:
                self.bus.publish(TOPIC_TIMING, event)
            return event
        raise TypeError(f"unexpected event type: {type(event)!r}")

    def run(self, sources: Iterable) -> dict:
        """Run every source to exhaustion through the pipeline.

        Args:
            sources: Iterable of source objects to merge and feed.

        Returns:
            A dict of event counts (``fix`` and ``timing`` totals).
        """
        for name, event in merge_streams(list(sources)):
            self.feed(event, name)
        return dict(self.counts)
