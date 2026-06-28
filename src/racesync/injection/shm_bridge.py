"""Shared-memory bridge from RaceSync phantom packets to a CSP Lua-readable frame.

CSP Lua (the Tier-B injection target in ``specs/13``) cannot reliably open UDP sockets, so
RaceSync's phantom packets are bridged into a fixed-layout binary frame in a memory-mapped
file that the Lua script reads each render frame.

The on-disk layout is deliberately tiny and fixed so both sides agree without negotiation:

* **Header** (``<4sHHII``): magic ``b"RSPH"``, version, car count, flags, sequence.
* **Records** (``<I5f`` each, ``MAX_CARS`` of them): car number, x, y, heading, speed,
  quality. Unused slots are zeroed.

Coordinates are RaceSync track-plane metres; the Lua side applies the calibrated transform
to AC world coordinates (``specs/13`` §13.4 Step 2).
"""

from __future__ import annotations

import struct
import zlib
from typing import Optional

from .base import PhantomState

MAGIC = b"RSPH"
VERSION = 1
MAX_CARS = 64

FLAG_CODE60 = 1 << 0
FLAG_CHEQUERED = 1 << 1

_HEADER = struct.Struct("<4sHHII")   # magic, version, count, flags, seq
_RECORD = struct.Struct("<I5f")      # car_num, x, y, heading, speed, quality
FRAME_SIZE = _HEADER.size + MAX_CARS * _RECORD.size


def car_number(car_id: str) -> int:
    """Map a car id to a stable unsigned 32-bit number for the binary frame.

    Numeric ids (e.g. ``"07"``) map to their integer value; non-numeric ids (e.g. ``"V1"``)
    map to a CRC32 hash so the Lua side still has a stable key.

    Args:
        car_id: The car identifier from the Position Model.

    Returns:
        An unsigned 32-bit integer identifying the car in the frame.
    """
    if car_id.isdigit():
        return int(car_id)
    return zlib.crc32(car_id.encode("utf-8")) & 0xFFFFFFFF


def pack_frame(world: dict[str, PhantomState], *, code60: bool = False,
               chequered: bool = False, seq: int = 0) -> bytes:
    """Serialise the current phantom world into a fixed-size binary frame.

    Args:
        world: Mapping of car id to its latest :class:`PhantomState`.
        code60: Whether the virtual field is under Code 60 (sets ``FLAG_CODE60``).
        chequered: Whether the timed finish has fallen (sets ``FLAG_CHEQUERED``).
        seq: Monotonic frame sequence number (lets the reader detect new frames).

    Returns:
        A ``FRAME_SIZE``-byte buffer: header followed by ``MAX_CARS`` records, with
        unused trailing slots zeroed. Cars beyond ``MAX_CARS`` are dropped.
    """
    flags = (FLAG_CODE60 if code60 else 0) | (FLAG_CHEQUERED if chequered else 0)
    items = list(world.items())[:MAX_CARS]
    buf = bytearray(FRAME_SIZE)
    _HEADER.pack_into(buf, 0, MAGIC, VERSION, len(items), flags, seq & 0xFFFFFFFF)
    offset = _HEADER.size
    for car_id, st in items:
        _RECORD.pack_into(buf, offset, car_number(car_id), st.x, st.y,
                          st.heading, st.speed or 0.0, st.quality)
        offset += _RECORD.size
    return bytes(buf)


def unpack_frame(data: bytes) -> dict:
    """Parse a binary frame back into a structured dict (the reference for the Lua reader).

    Args:
        data: A buffer at least ``FRAME_SIZE`` bytes long, as written by :func:`pack_frame`.

    Returns:
        A dict with keys ``version``, ``count``, ``seq``, ``code60``, ``chequered`` and
        ``cars`` (a list of per-car dicts with ``id``, ``x``, ``y``, ``heading``,
        ``speed``, ``quality``).

    Raises:
        ValueError: If the buffer is too short or the magic does not match.
    """
    if len(data) < _HEADER.size:
        raise ValueError("frame too short for header")
    magic, version, count, flags, seq = _HEADER.unpack_from(data, 0)
    if magic != MAGIC:
        raise ValueError(f"bad magic {magic!r}")
    cars = []
    offset = _HEADER.size
    for _ in range(min(count, MAX_CARS)):
        car_num, x, y, heading, speed, quality = _RECORD.unpack_from(data, offset)
        cars.append({"id": car_num, "x": x, "y": y, "heading": heading,
                     "speed": speed, "quality": quality})
        offset += _RECORD.size
    return {
        "version": version, "count": count, "seq": seq,
        "code60": bool(flags & FLAG_CODE60), "chequered": bool(flags & FLAG_CHEQUERED),
        "cars": cars,
    }


class ShmBridge:
    """Receives phantom packets and renders them into mmap frames for the CSP Lua reader.

    The bridge keeps a :class:`~racesync.injection.receiver.PhantomReceiver` to decode
    incoming packets, then packs the accumulated world into a frame on demand. The live
    UDP+mmap loop is :meth:`run` (Linux/Windows); :meth:`frame` is the pure, testable core.

    Attributes:
        receiver: The decoder accumulating phantom/global state.
        seq: The frame sequence counter, incremented per :meth:`frame`.
    """

    def __init__(self) -> None:
        """Initialise the bridge with a fresh receiver and zero sequence counter."""
        from .receiver import PhantomReceiver
        self.receiver = PhantomReceiver()
        self.seq = 0

    def ingest(self, data: bytes) -> None:
        """Decode one inbound phantom/global packet into the bridge's world state.

        Args:
            data: A raw packet as produced by the Assetto Corsa adapter's encoders.
        """
        self.receiver.ingest(data)

    def frame(self) -> bytes:
        """Pack the current world into a binary frame and advance the sequence counter.

        Returns:
            A ``FRAME_SIZE``-byte frame reflecting the latest world and global state.
        """
        self.seq += 1
        g = self.receiver.global_state
        return pack_frame(self.receiver.world(), code60=g.code60,
                          chequered=g.chequered, seq=self.seq)

    def run(self, file_path: str, host: str = "0.0.0.0", port: int = 9013,
            max_packets: Optional[int] = None) -> None:  # pragma: no cover - live I/O
        """Run the live UDP-to-mmap loop until interrupted.

        Binds a UDP socket, creates/truncates the mmap file to ``FRAME_SIZE``, and on each
        received packet updates the world and rewrites the frame.

        Args:
            file_path: Path to the memory-mapped frame file the Lua script reads.
            host: Interface to bind for inbound phantom packets.
            port: UDP port to bind (matches the AC adapter's target).
            max_packets: Optional cap on packets processed (for bounded test runs); when
                ``None`` the loop runs until interrupted.
        """
        import mmap
        import socket

        with open(file_path, "wb") as fh:
            fh.write(b"\x00" * FRAME_SIZE)
            fh.flush()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, port))
        with open(file_path, "r+b") as fh:
            mm = mmap.mmap(fh.fileno(), FRAME_SIZE)
            seen = 0
            try:
                while max_packets is None or seen < max_packets:
                    data, _addr = sock.recvfrom(2048)
                    self.ingest(data)
                    mm.seek(0)
                    mm.write(self.frame())
                    seen += 1
            finally:
                mm.close()
                sock.close()
