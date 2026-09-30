#!/usr/bin/env python3
"""
RoboMaster 2026 referee system bench tool (Communication Protocol V1.1.0, 2025-12-30).

Reads the referee UART (or a saved raw capture) and prints, logs, or plots every command.
For debugging on the bench; robot code should use referee_parser / ref_protocol directly.

Usage:
    python3 ref_comms.py                                # /dev/ttyUSB0 @ 115200, print everything
    python3 ref_comms.py -p /dev/ttyACM0 -b 921600      # VTM link
    python3 ref_comms.py --only 0x0201 0x0209           # only these cmd_ids
    python3 ref_comms.py --skip 0x0202 0x0203           # hide noisy ones
    python3 ref_comms.py --raw                          # also print raw frame hex
    python3 ref_comms.py --csv                          # also log every command to CSVs
    python3 ref_comms.py --save-raw                     # also save the raw byte stream
    python3 ref_comms.py --plot                         # live plot (default: power/heat/HP)
    python3 ref_comms.py --plot 0x0203.angle_deg 0x0208.allowance_17mm
    python3 ref_comms.py --replay raw.bin               # decode a saved raw capture
    python3 ref_comms.py --list                         # list all commands and fields

Printing: single-bit flags are shown only when set (flags=[...]); everything else is always shown.
Frames whose payload length doesn't match the layout are marked with "!len".
CSV (--csv): logs/referee_<timestamp>/ with one CSV per cmd (every field + raw_hex) + all_frames.csv.

Requires: pyserial (matplotlib for --plot; nothing extra for --replay)
"""

import argparse
import collections
import csv
import datetime as dt
import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import ExitStack
from typing import Self, TextIO

from ref_parser import Frame, RefereeParser
from ref_protocol import (
    CMD_ROBOT_INTERACTION,
    COMMANDS,
    SUB_COMMANDS,
    Message,
    Value,
    columns_of,
)

DEFAULT_PLOT = [
    "0x0202.buffer_energy",
    "0x0202.heat_17mm",
    "0x0202.heat_42mm",
    "0x0201.current_hp",
]


# ========================= Console Output =========================
def _fmt(name: str, v: Value) -> str:
    if name == "sub_id":
        return f"0x{v:04X}"
    if isinstance(v, float):
        return f"{v:.4g}" if abs(v) < 1e5 else f"{v:.6g}"
    return str(v)


def pretty(msg: Message) -> str:
    """Readable one-line summary: set single-bit flags collapsed into flags=[...]."""
    parts, set_flags = [], []
    for f in msg.fields:
        if f.keep and f.name in msg.values:
            v = msg.values[f.name]
            if f.bits and isinstance(v, int):
                parts.append(f"{f.name}=0x{v:X}")
            else:
                parts.append(f"{f.name}={_fmt(f.name, v)}")
        for bname, _, width in f.bits:
            if bname not in msg.values:
                continue
            if width > 1:
                parts.append(f"{bname}={msg.values[bname]}")
            elif msg.values[bname]:
                set_flags.append(bname)
    if any(width == 1 for f in msg.fields for _, _, width in f.bits):
        parts.append("flags=[" + ",".join(set_flags) + "]")
    return "  ".join(parts)


def list_commands() -> None:
    for cmd, (name, fields) in sorted(COMMANDS.items()):
        print(f"0x{cmd:04X} {name}: {', '.join(columns_of(fields))}")
        if cmd == CMD_ROBOT_INTERACTION:
            for sub, (sname, sfields) in sorted(SUB_COMMANDS.items()):
                print(f"    sub 0x{sub:04X} {sname}: {', '.join(columns_of(sfields))}")
            print("    sub 0x0200-0x02FF robot_interaction: payload")


# ========================= CSV output =========================
class CsvLogger:
    """One CSV per command (0x0301: per sub_id) plus all_frames.csv. Use as a context manager."""

    BASE = ("host_time", "t_s", "seq", "data_len")

    def __init__(self, outdir: str) -> None:
        self.outdir = outdir
        self._files = ExitStack()
        self._handles = []
        self.writers = {}  # key -> DictWriter
        self.t0 = time.monotonic()
        self.last_flush = 0.0
        self.all_writer = csv.writer(self._open("all_frames.csv"))
        self.all_writer.writerow(
            ["host_time", "t_s", "seq", "cmd_id", "name", "data_len", "frame_hex"]
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self._files.close()

    def _open(self, filename: str) -> TextIO:
        path = os.path.join(self.outdir, filename)
        # Lives as long as the logger; closed by self._files in __exit__.
        fh = self._files.enter_context(open(path, "w", newline=""))  # noqa: SIM115
        self._handles.append(fh)
        return fh

    def _writer(self, key, filename: str, columns: list[str]) -> csv.DictWriter:
        if key not in self.writers:
            w = csv.DictWriter(self._open(filename), columns, extrasaction="ignore")
            w.writeheader()
            self.writers[key] = w
        return self.writers[key]

    def log(self, frame: Frame, msg: Message) -> None:
        now = dt.datetime.now().astimezone().isoformat(timespec="milliseconds")
        t_s = f"{time.monotonic() - self.t0:.3f}"
        row = {
            "host_time": now,
            "t_s": t_s,
            "seq": frame.seq,
            "data_len": len(frame.data),
            **msg.values,
            "raw_hex": frame.data.hex(),
        }
        cols = [*self.BASE, *columns_of(msg.fields), "raw_hex"]

        if isinstance(sub_id := row.get("sub_id"), int):
            row["sub_id"] = f"0x{sub_id:04X}"
        # 0x0301 gets one file per sub_id, once the full 6-byte header decoded.
        _, has_sub, sub_name = msg.name.partition("/")
        if has_sub:
            key, fname = (
                (msg.cmd_id, sub_id),
                f"0x0301_sub_0x{sub_id:04X}_{sub_name}.csv",
            )
        else:
            key, fname = msg.cmd_id, f"0x{msg.cmd_id:04X}_{msg.name}.csv"

        self._writer(key, fname, cols).writerow(row)
        self.all_writer.writerow(
            [
                now,
                t_s,
                frame.seq,
                f"0x{msg.cmd_id:04X}",
                msg.name,
                len(frame.data),
                frame.raw.hex(),
            ]
        )
        if time.monotonic() - self.last_flush > 0.5:
            self.flush()

    def flush(self) -> None:
        for fh in self._handles:
            fh.flush()
        self.last_flush = time.monotonic()


# ========================= Live plot =========================
def run_plot(
    latest: dict, stop: threading.Event, specs: list[str], window_s: float = 30.0
) -> None:
    import matplotlib.pyplot as plt
    from matplotlib import animation

    series = []
    for s in specs:
        cmd, field = s.split(".", 1)
        series.append((s, int(cmd, 0), field))
    hist = {s: collections.deque() for s, _, _ in series}
    last_ts = {s: 0.0 for s, _, _ in series}
    t0 = time.time()

    fig, axes = plt.subplots(
        len(series), 1, sharex=True, figsize=(9, 2 + 1.6 * len(series)), squeeze=False
    )
    axes = axes[:, 0]
    lines = {}
    for ax, (label, _, _) in zip(axes, series, strict=True):
        (lines[label],) = ax.plot([], [], lw=1.5)
        ax.set_ylabel(label, fontsize=8)
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("time (s)")
    fig.suptitle("Referee system live data")

    def update(_):
        now = time.time() - t0
        for label, cmd, field in series:
            entry = latest.get(cmd)
            if (
                entry
                and entry[0] != last_ts[label]
                and isinstance(entry[1].get(field), (int, float))
            ):
                last_ts[label] = entry[0]
                hist[label].append((entry[0] - t0, entry[1][field]))
            while hist[label] and hist[label][0][0] < now - window_s:
                hist[label].popleft()
            if hist[label]:
                xs, ys = zip(*hist[label], strict=True)
                lines[label].set_data(xs, ys)
        for ax in axes:
            ax.set_xlim(max(0, now - window_s), max(window_s, now))
            ax.relim()
            ax.autoscale_view(scalex=False)
        return list(lines.values())

    # Must stay referenced until plt.show() returns, or the animation is garbage collected.
    _ani = animation.FuncAnimation(fig, update, interval=100, cache_frame_data=False)
    plt.show()
    stop.set()


# ========================= Main =========================
def reader_loop(
    source: Iterator[bytes],
    parser: RefereeParser,
    args: argparse.Namespace,
    latest: dict,
    stop: threading.Event,
    errors: list[BaseException],
    logger: CsvLogger | None,
    raw_fh,
) -> None:
    only = set(args.only or ())
    skip = set(args.skip or ())
    last_stats = time.monotonic()
    try:
        for chunk in source:
            if stop.is_set():
                break
            if not chunk:
                continue
            if raw_fh:
                raw_fh.write(chunk)
            for frame in parser.feed(chunk):
                msg = frame.decode()
                if logger:
                    logger.log(frame, msg)
                latest[frame.cmd_id] = (time.time(), msg.values)
                if (
                    (only and frame.cmd_id not in only)
                    or frame.cmd_id in skip
                    or args.quiet
                ):
                    continue
                t = time.strftime("%H:%M:%S")
                warn = "" if msg.length_ok else " !len"
                print(
                    f"[{t}] seq={frame.seq:3d} cmd=0x{frame.cmd_id:04X} len={len(frame.data):3d}{warn} "
                    f"{msg.name:22s} {pretty(msg)}",
                    flush=True,
                )
                if args.raw:
                    print(f"    raw: {frame.raw.hex(' ')}")
            if args.stats_every and time.monotonic() - last_stats > args.stats_every:
                print(f"--- stats: {parser.stats}", file=sys.stderr)
                last_stats = time.monotonic()
    except Exception as e:  # noqa: BLE001 (any failure here is reported by main())
        errors.append(e)
    finally:
        stop.set()


def cmd_id_arg(s: str) -> int:
    try:
        return int(s, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a cmd_id: {s!r} (e.g. 0x0202)") from None


def replay_source(path: str) -> Iterator[bytes]:
    with open(path, "rb") as fh:
        while chunk := fh.read(4096):
            yield chunk


def serial_source(ser) -> Iterator[bytes]:
    while True:
        yield ser.read(ser.in_waiting or 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="RoboMaster referee system bench tool")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="115200 standard link, 921600 VTM link",)
    ap.add_argument("--only", nargs="+", type=cmd_id_arg, metavar="CMD", help="only print these cmd_ids, e.g. 0x0202")
    ap.add_argument("--skip", nargs="+", type=cmd_id_arg, metavar="CMD", help="don't print these cmd_ids")
    ap.add_argument("--raw", action="store_true", help="also print raw frame hex")
    ap.add_argument("--quiet", action="store_true", help="print nothing per frame (use with --csv)")
    ap.add_argument("--csv", action="store_true", help="log every command to CSV files")
    ap.add_argument("-o", "--outdir", default=None, help="log folder (default logs/referee_<timestamp>)")
    ap.add_argument("--save-raw", action="store_true", help="save raw bytes to <outdir>/raw.bin")
    ap.add_argument("--plot", nargs="*", metavar="CMD.FIELD", help=f"live plot; default {' '.join(DEFAULT_PLOT)}")
    ap.add_argument("--replay", metavar="FILE", help="decode a raw capture instead of the serial port")
    ap.add_argument("--list", action="store_true", help="list all commands and fields, then exit")
    ap.add_argument("--stats-every", type=float, default=5.0, help="seconds between stats (0=off)")
    args = ap.parse_args()

    if args.list:
        list_commands()
        return 0

    parser = RefereeParser()
    latest, stop, errors = {}, threading.Event(), []
    with ExitStack() as resources:  # closes the port and log files on the way out
        if args.replay:
            source = replay_source(args.replay)
        else:
            try:
                import serial
            except ImportError:
                ap.error("pyserial is required to read a serial port (or use --replay)")
            try:
                ser = serial.Serial(
                    args.port,
                    args.baud,
                    bytesize=8,
                    parity="N",
                    stopbits=1,
                    timeout=0.1,
                )
            except serial.SerialException as e:
                ap.error(str(e))
            source = serial_source(resources.enter_context(ser))

        logger = raw_fh = None
        if args.csv or args.save_raw:
            outdir = args.outdir or os.path.join(
                "logs",
                "referee_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"),  # noqa: DTZ005 (local time is wanted)
            )
            os.makedirs(outdir, exist_ok=True)
            if args.csv:
                logger = resources.enter_context(CsvLogger(outdir))
            if args.save_raw:
                raw_fh = resources.enter_context(
                    open(os.path.join(outdir, "raw.bin"), "wb")
                )
            print(f"logging to {outdir}/", file=sys.stderr)

        th = threading.Thread(
            target=reader_loop,
            args=(source, parser, args, latest, stop, errors, logger, raw_fh),
            daemon=True,
        )
        th.start()
        try:
            if args.plot is not None:
                run_plot(latest, stop, args.plot or DEFAULT_PLOT)
            else:
                while th.is_alive():
                    th.join(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            th.join(1.0)
    print(f"\nfinal stats: {parser.stats}", file=sys.stderr)

    if errors:
        print(f"reader stopped: {errors[0]!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
