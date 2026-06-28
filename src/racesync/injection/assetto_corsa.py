"""Assetto Corsa injection adapter — Phase-1 spike target (specs/05 §5.3).

Assetto Corsa (original) is the spike's primary injection bet because its openness gives
*external car-state authorship* a realistic chance (specs/05 §5.2–5.3). Mainstream sims —
AC included — do **not** expose a supported "teleport any car to (x, y, θ)" call out of the
box, so true injection requires a **companion plugin/app running inside AC** (a Python app
via AC's app API, or a server-side UDP plugin) that receives our phantom states and moves
the corresponding entities. This adapter is the *client* side that streams phantom states
to that companion; the companion itself is built/validated during the spike.

Until the spike proves the companion works, treat this as **unvalidated scaffolding**: it
encodes and sends phantom states over UDP to a configured host:port. Sending succeeds
regardless of whether AC is listening — which is fine for measuring the *send* hop and for
exercising the wire format, but it does **not** demonstrate that AC renders the car. That
demonstration is the spike's job (specs/05 §5.4 S1).
"""

from __future__ import annotations

import json
import socket
from typing import Optional

from .base import GlobalSimState, PhantomState, SimInjectionAdapter


def encode_phantom_packet(state: PhantomState, seq: int = 0) -> bytes:
    """Encode a phantom state as a UDP payload for the AC companion plugin.

    The concrete on-wire schema is provisional (a JSON line keyed by car id) and will be
    finalised with the companion during the spike. It is kept pure and small so it can be
    unit-tested and swapped without touching the adapter logic.
    """
    payload = {
        "v": 1,
        "seq": seq,
        "car": state.car_id,
        "t": round(state.t, 4),
        "x": round(state.x, 3),
        "y": round(state.y, 3),
        "h": round(state.heading, 4),
        "spd": round(state.speed, 3) if state.speed is not None else None,
        "q": round(state.quality, 3),
    }
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def encode_global_packet(state: GlobalSimState) -> bytes:
    return (json.dumps({"v": 1, "global": {"code60": state.code60,
                                            "chequered": state.chequered}},
                       separators=(",", ":")) + "\n").encode("utf-8")


class AssettoCorsaAdapter(SimInjectionAdapter):
    """Streams phantom states to an AC companion plugin over UDP.

    Parameters
    ----------
    host, port:
        Where the AC companion plugin listens.
    sender:
        Optional injectable send-callable ``(bytes) -> None`` (used by tests to capture
        packets without opening a socket). When omitted, a real UDP socket is used.
    """

    name = "assetto-corsa"

    def __init__(self, host: str = "127.0.0.1", port: int = 9013, sender=None):
        self.host = host
        self.port = port
        self._sender = sender
        self._sock: Optional[socket.socket] = None
        self._seq = 0
        self.spawned: set[str] = set()
        self.sent_count = 0

    def connect(self) -> None:
        if self._sender is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def _send(self, data: bytes) -> None:
        if self._sender is not None:
            self._sender(data)
        elif self._sock is not None:
            self._sock.sendto(data, (self.host, self.port))
        else:
            raise RuntimeError("adapter not connected")
        self.sent_count += 1

    def spawn(self, car_id: str) -> None:
        self.spawned.add(car_id)

    def apply(self, state: PhantomState) -> None:
        self.spawned.add(state.car_id)
        self._send(encode_phantom_packet(state, seq=self._seq))
        self._seq += 1

    def set_global_state(self, state: GlobalSimState) -> None:
        self._send(encode_global_packet(state))

    def health(self) -> dict:
        return {"name": self.name, "host": self.host, "port": self.port,
                "sent": self.sent_count, "phantoms": len(self.spawned)}
