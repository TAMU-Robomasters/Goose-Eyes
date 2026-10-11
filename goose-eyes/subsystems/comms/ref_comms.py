#!/usr/bin/env python3
"""
RoboMaster 2026 referee system UART reader (Communication Protocol V1.1.0, 2025-12-30).

Reads the referee UART and yields decoded messages. Run directly to print them.
A dora node can reuse `read_messages` and send each Message's `values` as an output.

Usage:
    python3 ref_comms.py                            # /dev/ttyUSB0 @ 115200
    python3 ref_comms.py -p /dev/ttyACM0 -b 921600  # VTM link

Requires: pyserial
"""

import argparse
import sys
from collections.abc import Iterator

import serial
from ref_parser import RefereeParser
from ref_protocol import Message


def read_messages(
    port: str = "/dev/ttyUSB0", baud: int = 115200, parser: RefereeParser | None = None
) -> Iterator[Message]:
    """Yield every valid message from the referee UART, forever."""
    parser = parser or RefereeParser()
    with serial.Serial(port, baud, timeout=0.1) as ser:
        while True:
            for frame in parser.feed(ser.read(ser.in_waiting or 1)):
                yield frame.decode()


def main() -> int:
    ap = argparse.ArgumentParser(description="RoboMaster referee system UART reader")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="921600 for the VTM link")
    args = ap.parse_args()

    parser = RefereeParser()
    try:
        for msg in read_messages(args.port, args.baud, parser):
            warn = "" if msg.length_ok else " !len"
            print(f"0x{msg.cmd_id:04X} {msg.name}{warn} {msg.values}", flush=True)
    except KeyboardInterrupt:
        pass
    except serial.SerialException as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        print(f"stats: {parser.stats}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
