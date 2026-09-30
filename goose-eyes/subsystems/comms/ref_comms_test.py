#!/usr/bin/env python3
"""
Compare the cleaned-up referee tool against the original proof-of-concept script.
Only the outputs that should match are compared; a couple of intentional display
format differences are normalized away.

Checks:
  - known vectors: CRC-16 check value and one fully worked frame (independent of the original)
  - CLI vs original: printed frames, final parser stats, CSV files, --list
  - --save-raw writes back exactly the bytes it read
  - length_ok is right for every generated payload (the original has no equivalent)
  - feed() buffers its chunk even if the returned frames are never iterated
"""

import argparse
import csv
import importlib.util
import random
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ORIGINAL_PATH = HERE / "ref_comms_old.py"


def load_original(path: str | None) -> Path:
    if path:
        return Path(path).resolve()
    return ORIGINAL_PATH


def import_file(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_frame(seq: int, cmd_id: int, data: bytes) -> bytes:
    import ref_parser as new_parser

    header = bytes([0xA5]) + struct.pack("<HB", len(data), seq)
    header += bytes([new_parser.crc8(header)])
    body = header + struct.pack("<H", cmd_id) + data
    return body + struct.pack("<H", new_parser.crc16(body))


def layout_size(fields) -> int:
    return sum(f.size(0) for f in fields)


def make_payloads(old, rng: random.Random) -> list[tuple[int, bytes, bool]]:
    """(cmd_id, data, length matches its layout) for every command: exact, short, long."""
    payloads: list[tuple[int, bytes, bool]] = []
    for cmd_id, (_, fields) in old.COMMANDS.items():
        if fields is None:
            continue
        size = layout_size(fields)
        if size == 0:  # variable length ('x*'): any length is valid
            payloads.extend(
                (cmd_id, rng.randbytes(rng.randint(0, 40)), True) for _ in range(3)
            )
            continue
        payloads.append((cmd_id, rng.randbytes(size), True))
        payloads.append((cmd_id, rng.randbytes(max(size - 3, 0)), False))
        payloads.append((cmd_id, rng.randbytes(size + 2), False))

    for sub_id in [*old.SUB_COMMANDS, 0x0200, 0x0233, 0x02FF, 0x0999]:
        _, sub_fields = old.lookup_sub(sub_id)
        size = layout_size(sub_fields)
        header = struct.pack("<HHH", sub_id, 3, 0x103)
        if size == 0:
            payloads.append((0x0301, header + rng.randbytes(10), True))
            continue
        payloads.append((0x0301, header + rng.randbytes(size), True))
        payloads.append((0x0301, header + rng.randbytes(size - 1), False))

    payloads.append((0x0301, b"", False))
    payloads.append((0x0301, b"\x20\x01\x01", False))
    payloads.append((0x0BAD, rng.randbytes(7), True))
    return payloads


def make_stream(payloads, rng: random.Random, repeat: int) -> bytes:
    items = payloads * repeat
    rng.shuffle(items)
    stream = bytearray()
    for seq, (cmd_id, data, _) in enumerate(items):
        if rng.random() < 0.05:
            stream += rng.randbytes(rng.randint(1, 30))
        frame = bytearray(build_frame(seq & 0xFF, cmd_id, data))
        if rng.random() < 0.03:
            frame[rng.randrange(len(frame))] ^= 1 << rng.randrange(8)
        stream += frame
        if rng.random() < 0.02:
            stream += b"\xa5"
    return bytes(stream)


def run_cli(script: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def normalize_console(text: str) -> list[str]:
    lines: list[str] = []
    skip_raw = False
    for line in text.splitlines():
        if skip_raw and line.startswith("    raw:"):
            continue
        line = re.sub(r"^\[\d\d:\d\d:\d\d\] ", "", line)
        line = line.replace(" !len", "")
        if re.match(r"seq=\s*\d+ cmd=0x0301 len=\s*[0-5] ", line):
            skip_raw = True
            continue
        skip_raw = False
        if line:
            lines.append(line)
    return lines


def normalize_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    return [
        {k: v for k, v in row.items() if k not in {"host_time", "t_s"}} for row in rows
    ]


def compare_dirs(old_dir: Path, new_dir: Path) -> list[str]:
    problems: list[str] = []
    old_files = {p.name for p in old_dir.glob("*.csv")}
    new_files = {p.name for p in new_dir.glob("*.csv")}
    if old_files != new_files:
        return [f"CSV file set differs: {sorted(old_files ^ new_files)}"]

    skip = {"0x0301_robot_interaction.csv"}
    for name in sorted(old_files - skip):
        if normalize_csv_rows(old_dir / name) != normalize_csv_rows(new_dir / name):
            problems.append(f"CSV mismatch: {name}")
    return problems


def final_stats(stderr: str) -> str | None:
    """The parser's error counters, printed by both scripts as the last stderr line."""
    lines = [line for line in stderr.splitlines() if line.startswith("final stats:")]
    return lines[-1] if lines else None


def check_known_vectors() -> list[str]:
    """Checks that don't rely on the original being right."""
    import ref_parser as new_parser

    problems: list[str] = []
    if (crc := new_parser.crc16(b"123456789")) != 0x6F91:
        problems.append(f"crc16 check value {crc:#06x} != 0x6f91 (CRC-16/MCRF4XX)")
    # 0x0203 robot_pos x=1.5 y=2.0 angle=90, seq 7, per Table 1-1:
    # SOF, data_len 12, seq, CRC8 | cmd_id | three little-endian floats | CRC16
    expected = bytes.fromhex(
        "a5 0c 00 07 fb  03 02  00 00 c0 3f  00 00 00 40  00 00 b4 42  e8 24"
    )
    built = build_frame(7, 0x0203, struct.pack("<fff", 1.5, 2.0, 90.0))
    if built != expected:
        problems.append(f"robot_pos frame {built.hex(' ')} != {expected.hex(' ')}")
    frames = new_parser.RefereeParser().feed_all(expected)
    values = frames[0].decode().values if frames else None
    if values != {"x_m": 1.5, "y_m": 2.0, "angle_deg": 90.0}:
        problems.append(f"robot_pos decoded to {values}")
    return problems


def check_length_ok(payloads) -> list[str]:
    import ref_protocol as new_protocol

    problems: list[str] = []
    for cmd_id, data, expected in payloads:
        got = new_protocol.decode(cmd_id, data).length_ok
        if got != expected:
            problems.append(f"length_ok={got} for cmd 0x{cmd_id:04X} len {len(data)}")
    return problems


def check_feed_buffers(stream: bytes) -> list[str]:
    """A caller that ignores feed()'s return value must not lose the chunk."""
    import ref_parser as new_parser

    parser = new_parser.RefereeParser()
    parser.feed(stream[:5000])  # return value deliberately ignored
    if not parser.buf and parser.stats["ok"] == 0:
        return ["feed() dropped its chunk because the returned frames weren't iterated"]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify that the new referee decoder produces the same output as the original script."
    )
    ap.add_argument(
        "--original",
        help=f"Original ref_comms.py path (default: {ORIGINAL_PATH.name})",
    )
    ap.add_argument(
        "--seed", type=int, default=1, help="Random seed for the generated test stream"
    )
    ap.add_argument(
        "--repeat", type=int, default=20, help="Copies of each payload in the stream"
    )
    ap.add_argument(
        "--keep", metavar="DIR", help="Keep the generated stream and output in DIR"
    )
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(args.keep).resolve() if args.keep else Path(tmp)
        workdir.mkdir(parents=True, exist_ok=True)

        original = load_original(args.original)
        old_mod = import_file(original, "ref_comms_original")

        rng = random.Random(args.seed)
        payloads = make_payloads(old_mod, rng)
        stream = make_stream(payloads, rng, args.repeat)
        capture = workdir / "stream.bin"
        capture.write_bytes(stream)

        common = ["--replay", str(capture), "--csv", "--raw", "--stats-every", "0"]
        old_run = run_cli(original, [*common, "-o", "csv_old"], workdir)
        new_run = run_cli(
            HERE / "ref_comms.py", [*common, "-o", "csv_new", "--save-raw"], workdir
        )

        problems: list[str] = []
        problems.extend(check_known_vectors())
        problems.extend(check_length_ok(payloads))
        problems.extend(check_feed_buffers(stream))
        if old_run.returncode != 0:
            problems.append(
                f"old script exited {old_run.returncode}: {old_run.stderr.strip()}"
            )
        if new_run.returncode != 0:
            problems.append(
                f"new script exited {new_run.returncode}: {new_run.stderr.strip()}"
            )

        old_lines = normalize_console(old_run.stdout)
        new_lines = normalize_console(new_run.stdout)
        if old_lines != new_lines:
            diffs = [
                f"line {i}: {o!r} != {n!r}"
                for i, (o, n) in enumerate(zip(old_lines, new_lines, strict=False))
                if o != n
            ]
            problems.extend(
                diffs
                or [f"stdout line count differs: {len(old_lines)} != {len(new_lines)}"]
            )

        old_stats, new_stats = final_stats(old_run.stderr), final_stats(new_run.stderr)
        if old_stats != new_stats:
            problems.append(f"parser stats differ: {old_stats} != {new_stats}")

        raw_copy = workdir / "csv_new" / "raw.bin"
        if not raw_copy.exists() or raw_copy.read_bytes() != stream:
            problems.append("--save-raw output differs from the input stream")

        problems.extend(compare_dirs(workdir / "csv_old", workdir / "csv_new"))

        old_list = run_cli(original, ["--list"], workdir).stdout.splitlines()
        new_list = run_cli(
            HERE / "ref_comms.py", ["--list"], workdir
        ).stdout.splitlines()
        old_list = [line for line in old_list if not line.startswith("0x0301 ")]
        new_list = [line for line in new_list if not line.startswith("0x0301 ")]
        if old_list != new_list:
            problems.append("--list output differs")

    if problems:
        print("FAIL")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("PASS: new output matches the original script")
    return 0


if __name__ == "__main__":
    sys.exit(main())
