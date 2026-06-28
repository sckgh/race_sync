"""PhantomReceiver — the sim-side endpoint that consumes injected phantom states.

This is the receiving counterpart to ``SimInjectionAdapter``: it ingests the UDP packets
RaceSync sends and maintains the current world state (each phantom's position + the global
Code 60 / chequered state). The Assetto Corsa companion app uses exactly this logic
(reimplemented in AC's Python) to know where to draw / move phantoms.

Having it here, dependency-free and tested, means the entire RaceSync → sim wire loop
(encode → transport → decode → world state) is verifiable without a simulator.
"""

from __future__ import annotations

from typing import Optional

from .assetto_corsa import decode_global_packet, decode_phantom_packet
from .base import GlobalSimState, PhantomState


class PhantomReceiver:
    """Decodes phantom/global packets and tracks current sim-side world state."""

    def __init__(self) -> None:
        self.cars: dict[str, PhantomState] = {}
        self.global_state = GlobalSimState()
        self._last_seq: dict[str, int] = {}
        self.received = 0
        self.dropped_stale = 0

    def ingest(self, data: bytes):
        """Process one received packet. Returns the applied state, or None if dropped."""
        decoded = decode_phantom_packet(data)
        if decoded is not None:
            state, seq = decoded
            last = self._last_seq.get(state.car_id)
            if last is not None and seq < last:
                self.dropped_stale += 1  # out-of-order/stale on a UDP path — discard
                return None
            self._last_seq[state.car_id] = seq
            self.cars[state.car_id] = state
            self.received += 1
            return state
        glob = decode_global_packet(data)
        if glob is not None:
            self.global_state = glob
            self.received += 1
            return glob
        return None

    def world(self) -> dict[str, PhantomState]:
        return dict(self.cars)

    def latest(self, car_id: str) -> Optional[PhantomState]:
        return self.cars.get(car_id)
