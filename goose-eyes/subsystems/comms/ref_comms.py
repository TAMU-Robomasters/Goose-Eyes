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
    port: str = "/dev/ttyTHS1", baud: int = 115200, parser: RefereeParser | None = None
) -> Iterator[Message]:
    """Yield every valid message from the referee UART, forever."""
    parser = parser or RefereeParser()
    with serial.Serial(port, baud, timeout=0.1) as ser:
        while True:
            for frame in parser.feed(ser.read(ser.in_waiting or 1)):
                yield frame.decode()


def cmd_id_arg(s: str) -> int:
    try:
        return int(s, 0)  # accepts 0x0201 or 513
    except ValueError:
        raise argparse.ArgumentTypeError(f"bad cmd_id: {s!r}") from None


def main() -> int:
    ap = argparse.ArgumentParser(description="RoboMaster referee system UART reader")
    ap.add_argument("-p", "--port", default="/dev/ttyTHS1")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="921600 for the VTM link")
    ap.add_argument("--only", nargs="+", type=cmd_id_arg, metavar="CMD", help="only print these cmd_ids, e.g. 0x0202")
    ap.add_argument("--skip", nargs="+", type=cmd_id_arg, metavar="CMD", help="don't print these cmd_ids")
    args = ap.parse_args()
    only, skip = set(args.only or ()), set(args.skip or ())

    parser = RefereeParser()
    try:
        for msg in read_messages(args.port, args.baud, parser):
            if (only and msg.cmd_id not in only) or msg.cmd_id in skip:
                continue
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
