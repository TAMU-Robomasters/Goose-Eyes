"""
RoboMaster 2026 referee system frame parser.

Communication protocol format (Communication Protocol V1.1.0, 2025-12-30, Table 1-1):
Protocol Doc Link: https://bbs.robomaster.com/wiki/20204847/811363

 |──────────── header (5 bytes) ───────────|
 │ 0xA5 │ data_len (u16) │ seq (u8) │ CRC8 │ cmd_id (u16) │ data (data_len bytes) │ CRC16 (u16) │
   SOF                                ^                                                  ^
                         covers the first 4 bytes                  covers everything before it

All multi-byte values are little-endian. UART: 115200 8N1 (standard link), 921600 (VTM link).

Usage:
    parser = RefereeParser()
    for frame in parser.feed(ser.read(ser.in_waiting or 1)):
        msg = frame.decode()        # -> ref_protocol.Message
        msg.name, msg.values        # "robot_status", {"robot_id": 3, "current_hp": 200, ...}
"""

from collections.abc import Iterator
from dataclasses import dataclass

from ref_protocol import Message, decode

SOF = 0xA5
HEADER_LEN = 5
CMD_ID_LEN = 2
CRC16_LEN = 2
MAX_DATA_LEN = 512  # Sanity bound, largest data payload is 150 bytes (0x0310)


# ========================= CRC Utils =========================
# Generated tables; verified identical to Appendix I of the protocol PDF.
def _make_table(poly: int) -> list[int]:
    table = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ poly if c & 1 else c >> 1
        table.append(c)
    return table


CRC8_TAB = _make_table(0x8C)  # x^8+x^5+x^4+1 reflected, init 0xFF
CRC16_TAB = _make_table(0x8408)  # CRC-16/MCRF4XX, init 0xFFFF


def crc8(data: bytes, crc: int = 0xFF) -> int:
    for b in data:
        crc = CRC8_TAB[crc ^ b]
    return crc


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        crc = (crc >> 8) ^ CRC16_TAB[(crc ^ b) & 0xFF]
    return crc


# ========================= Frame Parser =========================
@dataclass(frozen=True)
class Frame:
    seq: int
    cmd_id: int
    data: bytes  # data segment only
    raw: bytes  # whole frame, header through CRC16

    def decode(self) -> Message:
        return decode(self.cmd_id, self.data)


class RefereeParser:
    """Reassembles frames from an arbitrarily chunked byte stream.

    Resyncs on the SOF byte after junk or a failed CRC; `stats` counts what was dropped.
    """

    def __init__(self) -> None:
        self.buf = bytearray()
        self.stats = {
            "ok": 0,
            "crc8_fail": 0,
            "crc16_fail": 0,
            "bad_len": 0,
            "seq_gaps": 0,
            "junk_bytes": 0,
        }
        self.last_seq: int | None = None

    def feed(self, chunk: bytes) -> Iterator[Frame]:
        """Buffer `chunk` and return an iterator over the complete frames now available.

        Not a generator itself, so the chunk is buffered even if the result is never
        iterated. Frames are parsed lazily, one per next(), so the first is available
        without parsing the rest of the chunk.
        """
        self.buf += chunk
        return self._frames()

    def _frames(self) -> Iterator[Frame]:
        while (frame := self._next_frame()) is not None:
            yield frame

    def feed_all(self, chunk: bytes) -> list[Frame]:
        """Helper for batched frames (Used in tester)."""
        return list(self.feed(chunk))

    def _next_frame(self) -> Frame | None:
        while True:
            start = self.buf.find(SOF)
            if start < 0:
                self.stats["junk_bytes"] += len(self.buf)
                self.buf.clear()
                return None
            if start:
                self.stats["junk_bytes"] += start
                del self.buf[:start]
            if len(self.buf) < HEADER_LEN:
                return None

            # A bad header means this SOF was a data byte: drop it and search again.
            if crc8(self.buf[: HEADER_LEN - 1]) != self.buf[HEADER_LEN - 1]:
                self.stats["crc8_fail"] += 1
                del self.buf[0]
                continue
            data_len = int.from_bytes(self.buf[1:3], "little")
            if data_len > MAX_DATA_LEN:
                self.stats["bad_len"] += 1
                del self.buf[0]
                continue

            frame_len = HEADER_LEN + CMD_ID_LEN + data_len + CRC16_LEN
            if len(self.buf) < frame_len:
                return None
            raw = bytes(self.buf[:frame_len])
            if crc16(raw[:-CRC16_LEN]) != int.from_bytes(raw[-CRC16_LEN:], "little"):
                self.stats["crc16_fail"] += 1
                del self.buf[0]
                continue
            del self.buf[:frame_len]

            seq = raw[3]
            if self.last_seq is not None and seq != (self.last_seq + 1) & 0xFF:
                self.stats["seq_gaps"] += 1
            self.last_seq = seq
            self.stats["ok"] += 1
            data_start = HEADER_LEN + CMD_ID_LEN
            return Frame(
                seq=seq,
                cmd_id=int.from_bytes(raw[HEADER_LEN:data_start], "little"),
                data=raw[data_start:-CRC16_LEN],
                raw=raw,
            )
