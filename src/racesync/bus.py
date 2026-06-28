"""A tiny synchronous in-process publish/subscribe event bus.

This is the internal bus from ``specs/03-system-architecture.md``: every component
communicates through it rather than point-to-point, which makes the bus the natural
place for logging, replay and the audit trail. It is deliberately minimal and
synchronous — easy to reason about and test. A networked/broker-backed transport for
the edge<->cloud hop can implement the same publish/subscribe shape later.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Iterable


# Topic constants for the core message families (specs/03 §3.3).
TOPIC_POSITION = "position.update"
TOPIC_TIMING = "timing.event"
TOPIC_STATE = "state.transition"
TOPIC_SIM_TELEMETRY = "sim.telemetry"
TOPIC_OPERATOR = "operator.command"
TOPIC_HEALTH = "health"


class EventBus:
    """Synchronous topic-based pub/sub.

    Handlers are invoked in subscription order on the publishing thread. A handler that
    raises does not prevent other handlers from running; the error is collected and
    re-raised as an aggregate after dispatch so a faulty consumer cannot silently
    swallow events (the backbone must never lose state changes — specs/09 §9.3).
    """

    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[object], None]]] = defaultdict(list)
        self._log: list[tuple[str, object]] = []
        self._record = False

    def subscribe(self, topic: str, handler: Callable[[object], None]) -> Callable[[], None]:
        """Subscribe a handler to a topic.

        Args:
            topic: The topic to subscribe to.
            handler: Callable invoked with each event published on the topic.

        Returns:
            A callable that, when invoked, unsubscribes the handler.
        """
        self._subs[topic].append(handler)

        def _unsub() -> None:
            try:
                self._subs[topic].remove(handler)
            except ValueError:
                pass

        return _unsub

    def publish(self, topic: str, event: object) -> None:
        """Dispatch an event to every handler subscribed to a topic.

        Handlers run in subscription order. A handler that raises does not stop the
        others; all errors are collected and re-raised together once dispatch finishes.

        Args:
            topic: The topic to publish on.
            event: The event object passed to each handler.

        Raises:
            ExceptionGroup: If one or more handlers raised during dispatch.
        """
        if self._record:
            self._log.append((topic, event))
        errors: list[Exception] = []
        for handler in list(self._subs.get(topic, ())):
            try:
                handler(event)
            except Exception as exc:  # noqa: BLE001 - aggregate and re-raise below
                errors.append(exc)
        if errors:
            raise ExceptionGroup(f"{len(errors)} handler(s) failed on {topic!r}", errors)

    # -- audit/replay support (specs/03, specs/09 §9.10) -------------------- #

    def start_recording(self) -> None:
        """Begin capturing every published event for the audit log / replay."""
        self._record = True

    def history(self, topic: str | None = None) -> Iterable[tuple[str, object]]:
        """Return the recorded (topic, event) pairs, optionally filtered by topic.

        Args:
            topic: If given, return only events published on this topic; otherwise
                return the full history.

        Returns:
            A list of (topic, event) pairs in publication order.
        """
        if topic is None:
            return list(self._log)
        return [(t, e) for (t, e) in self._log if t == topic]
