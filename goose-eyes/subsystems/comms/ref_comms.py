#!/usr/bin/env python3
"""
RoboMaster 2026 Referee System parser (Communication Protocol V1.1.0, 2025-12-30).

Decodes EVERY command in the protocol: 0x0001-0x020E, 0x0301 (+ all sub-content IDs),
0x0302-0x0310, 0x0F01/0x0F02, 0x0A01-0x0A06. Unknown cmd_ids are shown as hex.

Frame: SOF(0xA5) | data_len(u16 LE) | seq | CRC8 | cmd_id(u16 LE) | data | CRC16(LE)

Usage:
    python3 referee_parser.py                                # /dev/ttyUSB0 @ 115200, print everything
    python3 referee_parser.py -p /dev/ttyACM0 -b 921600      # VTM link
    python3 referee_parser.py --only 0x0201 0x0209           # only these cmd_ids
    python3 referee_parser.py --skip 0x0202 0x0203           # hide noisy ones
    python3 referee_parser.py --raw                          # also print raw frame hex
    python3 referee_parser.py --csv                          # also log every command to CSVs
    python3 referee_parser.py --plot                         # live plot (default: power/heat/HP)
    python3 referee_parser.py --plot 0x0203.angle_deg 0x0208.allowance_17mm
    python3 referee_parser.py --replay raw.bin               # decode a saved raw capture
    python3 referee_parser.py --list                         # list all commands and fields

Printing: single-bit flags are shown only when set (flags=[...]); everything else is always shown.
CSV (--csv): logs/referee_<timestamp>/ with one CSV per cmd (every field + raw_hex) + all_frames.csv.

Requires: pip install pyserial   (matplotlib for --plot; nothing for --replay)
"""
import argparse
import collections
import csv
import datetime as dt
import os
import struct
import sys
import threading
import time

# ============================================================== CRC
# Generated tables; verified identical to Appendix I of the protocol PDF.
def _make_table(poly):
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ poly if c & 1 else c >> 1
        t.append(c)
    return t

CRC8_TAB = _make_table(0x8C)      # x^8+x^5+x^4+1 reflected, init 0xFF
CRC16_TAB = _make_table(0x8408)   # CRC-16/MCRF4XX, init 0xFFFF


def crc8(data, crc=0xFF):
    for b in data:
        crc = CRC8_TAB[crc ^ b]
    return crc


def crc16(data, crc=0xFFFF):
    for b in data:
        crc = (crc >> 8) ^ CRC16_TAB[(crc ^ b) & 0xFF]
    return crc


# ============================================================== field specs
class F:
    """One field of a packed struct.

    fmt: struct char(s) ('B','H','I','Q','b','h','f', '49b' ...) or custom:
         'aN' ASCII string of N bytes, 'uN' UTF-16LE text of N bytes,
         'xN' N bytes as hex, 'x*' all remaining bytes as hex.
    bits: [(name, lo_bit, width), ...] extracted from the integer value.
    keep: False = only emit the bit fields, not the raw integer.
    """
    def __init__(self, name, fmt, bits=None, keep=True):
        self.name, self.fmt, self.bits, self.keep = name, fmt, bits or [], keep

    def columns(self):
        return ([self.name] if self.keep else []) + [b[0] for b in self.bits]

    def size(self, remaining):
        k = self.fmt[0]
        if self.fmt == "x*":
            return remaining
        if k in "au" or (k == "x" and self.fmt[1:].isdigit()):
            return int(self.fmt[1:])
        return struct.calcsize("<" + self.fmt)

    def decode(self, raw):
        k = self.fmt[0]
        if k == "a":
            val = raw.split(b"\0")[0].decode("ascii", "replace")
        elif k == "u":
            val = raw.decode("utf-16-le", "replace").split("\0")[0]
        elif k == "x":
            val = raw.hex()
        else:
            vals = struct.unpack("<" + self.fmt, raw)
            val = vals[0] if len(vals) == 1 else " ".join(str(v) for v in vals)
        out = {}
        if self.keep:
            out[self.name] = val
        for name, lo, width in self.bits:
            out[name] = (val >> lo) & ((1 << width) - 1)
        return out


def flags(names, start=0):
    """Single-bit flags starting at bit `start`."""
    return [(n, start + i, 1) for i, n in enumerate(names)]


def decode_fields(data, fields):
    """Decode as many fields as the data holds; missing trailing fields stay blank."""
    out, off = {}, 0
    for f in fields:
        n = f.size(len(data) - off)
        if off + n > len(data):
            break
        out.update(f.decode(data[off:off + n]))
        off += n
    return out


# ---------------------------------------------------------------- per-command tables
# Bit-field names paraphrase the descriptions in the protocol tables.

RFID_BITS = flags([
    "own_base", "own_central_highland", "opp_central_highland",
    "own_trapezoid_highland", "opp_trapezoid_highland",
    "own_ramp_before", "own_ramp_after", "opp_ramp_before", "opp_ramp_after",
    "own_cross_trapezoid_below", "own_cross_central_above",
    "opp_cross_central_below", "opp_cross_central_above",
    "own_road_below", "own_road_above", "opp_road_below", "opp_road_above",
    "own_fortress", "own_outpost", "own_resupply_nonoverlap", "own_resupply_overlap",
    "own_assembly", "opp_assembly", "central_buff_rmul", "opp_fortress", "opp_outpost",
    "own_tunnel_road_low", "own_tunnel_road_high",
    "own_tunnel_trapezoid_low", "own_tunnel_trapezoid_high",
    "opp_tunnel_road_low", "opp_tunnel_road_high",
])

KEY_BITS = flags(["key_" + k for k in
                  ["W", "S", "A", "D", "Shift", "Ctrl", "Q", "E",
                   "R", "F", "G", "Z", "X", "C", "V", "B"]])


def buff_fields(prefix):
    return [F(f"{prefix}recovery_buff", "B"), F(f"{prefix}cooling_buff", "H"),
            F(f"{prefix}defense_buff", "B"), F(f"{prefix}vulnerability_buff", "B"),
            F(f"{prefix}attack_buff", "H")]


def figure_fields(n):
    out = []
    for i in range(n):
        p = f"fig{i}_" if n > 1 else ""
        out += [
            F(f"{p}name", "a3"),
            F(f"{p}w1", "I", [(f"{p}operate_type", 0, 3), (f"{p}figure_type", 3, 3),
                              (f"{p}layer", 6, 4), (f"{p}color", 10, 4),
                              (f"{p}details_a", 14, 9), (f"{p}details_b", 23, 9)], keep=False),
            F(f"{p}w2", "I", [(f"{p}width", 0, 10), (f"{p}start_x", 10, 11),
                              (f"{p}start_y", 21, 11)], keep=False),
            F(f"{p}w3", "I", [(f"{p}details_c", 0, 10), (f"{p}details_d", 10, 11),
                              (f"{p}details_e", 21, 11)], keep=False),
        ]
    return out


COMMANDS = {
    0x0001: ("game_status", [
        F("game_type_progress", "B", [("game_type", 0, 4), ("game_progress", 4, 4)], keep=False),
        F("stage_remain_time", "H"), F("sync_timestamp", "Q")]),
    0x0002: ("game_result", [F("winner", "B")]),
    0x0003: ("game_robot_hp", [F(n, "H") for n in [
        "hero_1_hp", "engineer_2_hp", "infantry_3_hp", "infantry_4_hp",
        "reserved", "sentry_7_hp", "outpost_hp", "base_hp"]]),
    0x0101: ("event_data", [F("event_data", "I", [
        ("resupply_nonoverlap_occupied", 0, 1), ("resupply_overlap_occupied", 1, 1),
        ("resupply_rmul_occupied", 2, 1), ("small_rune_status", 3, 2),
        ("large_rune_status", 5, 2), ("central_highland_status", 7, 2),
        ("trapezoid_highland_status", 9, 2), ("opp_dart_last_hit_time", 11, 9),
        ("opp_dart_last_hit_target", 20, 3), ("central_buff_rmul_status", 23, 2),
        ("fortress_buff_status", 25, 2), ("outpost_buff_status", 27, 2),
        ("base_buff_occupied", 29, 1)])]),
    0x0104: ("referee_warning", [F("level", "B"), F("offending_robot_id", "B"), F("count", "B")]),
    0x0105: ("dart_info", [F("dart_remaining_time", "B"), F("dart_info", "H", [
        ("own_dart_last_target", 0, 3), ("opp_hit_count", 3, 3), ("selected_target", 6, 2)])]),
    0x0201: ("robot_status", [
        F("robot_id", "B"), F("robot_level", "B"), F("current_hp", "H"), F("maximum_hp", "H"),
        F("barrel_cooling_value", "H"), F("barrel_heat_limit", "H"), F("chassis_power_limit", "H"),
        F("power_output", "B", flags(["gimbal_output", "chassis_output", "shooter_output"]))]),
    0x0202: ("power_heat", [
        F("reserved_0", "H"), F("reserved_1", "H"), F("reserved_2", "f"),
        F("buffer_energy", "H"), F("heat_17mm", "H"), F("heat_42mm", "H")]),
    # Real referee sends 12 bytes (Table 1-13); the 16 in Table 1-4 is a doc error.
    0x0203: ("robot_pos", [F("x_m", "f"), F("y_m", "f"), F("angle_deg", "f")]),
    0x0204: ("buff", buff_fields("") + [F("remaining_energy", "B", flags(
        ["energy_ge_125", "energy_ge_100", "energy_ge_50", "energy_ge_30",
         "energy_ge_15", "energy_ge_5", "energy_ge_1"]))]),
    0x0206: ("hurt_data", [F("hurt", "B", [("armor_id", 0, 4), ("hp_deduction_reason", 4, 4)],
                             keep=False)]),
    0x0207: ("shoot_data", [F("projectile_type", "B"), F("shooter_number", "B"),
                            F("launching_frequency", "B"), F("projectile_speed", "f")]),
    0x0208: ("projectile_allowance", [F("allowance_17mm", "H"), F("allowance_42mm", "H"),
                                      F("remaining_gold_coin", "H"), F("allowance_fortress", "H")]),
    0x0209: ("rfid_status", [F("rfid_status", "I", RFID_BITS),
                             F("rfid_status_2", "B", flags(["opp_tunnel_trapezoid_low",
                                                            "opp_tunnel_trapezoid_high"]))]),
    0x020A: ("dart_client_cmd", [F("dart_launch_opening_status", "B"), F("reserved", "B"),
                                 F("target_change_time", "H"), F("latest_launch_cmd_time", "H")]),
    0x020B: ("ground_robot_position", [F(n, "f") for n in [
        "hero_x", "hero_y", "engineer_x", "engineer_y", "infantry_3_x", "infantry_3_y",
        "infantry_4_x", "infantry_4_y", "reserved_0", "reserved_1"]]),
    0x020C: ("radar_mark_data", [F("mark", "H", flags(
        ["opp_hero_vulnerable", "opp_engineer_vulnerable", "opp_infantry_3_vulnerable",
         "opp_infantry_4_vulnerable", "opp_sentry_vulnerable",
         "own_hero_tracked", "own_engineer_tracked", "own_infantry_3_tracked",
         "own_infantry_4_tracked", "own_sentry_tracked"]))]),
    0x020D: ("sentry_info", [
        F("sentry_info", "I", [("exchanged_projectiles", 0, 11), ("remote_projectile_exchanges", 11, 4),
                               ("remote_hp_exchanges", 15, 4), ("can_free_respawn", 19, 1),
                               ("can_instant_respawn", 20, 1), ("instant_respawn_cost", 21, 10)]),
        F("sentry_info_2", "H", [("sentry_mode", 12, 2), ("power_rune_activatable", 14, 1)])]),
    0x020E: ("radar_info", [F("radar_info", "B", [
        ("double_vuln_chances", 0, 2), ("opp_double_vuln_active", 2, 1),
        ("own_encryption_level", 3, 2), ("key_modifiable", 5, 1)])]),
    0x0301: ("robot_interaction", None),   # handled via SUB_COMMANDS
    0x0302: ("custom_controller_data", [F("data", "x*")]),
    0x0303: ("map_command", [F("target_x", "f"), F("target_y", "f"), F("cmd_keyboard", "B"),
                             F("opponent_robot_id", "B"), F("source_id", "H")]),
    0x0304: ("remote_control", [F("mouse_x", "h"), F("mouse_y", "h"), F("mouse_z", "h"),
                                F("left_button_down", "b"), F("right_button_down", "b"),
                                F("keyboard_value", "H", KEY_BITS), F("reserved", "H")]),
    0x0305: ("map_robot_data", [F(n, "H") for n in [
        "hero_x_cm", "hero_y_cm", "engineer_x_cm", "engineer_y_cm",
        "infantry_3_x_cm", "infantry_3_y_cm", "infantry_4_x_cm", "infantry_4_y_cm",
        "infantry_5_x_cm", "infantry_5_y_cm", "sentry_x_cm", "sentry_y_cm"]]),
    0x0306: ("custom_client_data", [
        F("key_value", "H", [("key_1", 0, 8), ("key_2", 8, 8)]),
        F("mouse_x_word", "H", [("mouse_x_px", 0, 12), ("mouse_left", 12, 4)], keep=False),
        F("mouse_y_word", "H", [("mouse_y_px", 0, 12), ("mouse_right", 12, 4)], keep=False),
        F("reserved", "H")]),
    0x0307: ("map_path_data", [F("intention", "B"), F("start_x_dm", "H"), F("start_y_dm", "H"),
                               F("delta_x_dm", "49b"), F("delta_y_dm", "49b"), F("sender_id", "H")]),
    0x0308: ("custom_info", [F("sender_id", "H"), F("receiver_id", "H"), F("text", "u30")]),
    0x0309: ("robot_custom_data", [F("data", "x*")]),
    0x0310: ("robot_custom_data_2", [F("data", "x*")]),
    0x0F01: ("vtm_set_channel", [F("value", "B")]),
    0x0F02: ("vtm_query_channel", [F("channel", "B")]),
    0x0A01: ("opp_positions", [F(n, "H") for n in [
        "hero_x_cm", "hero_y_cm", "engineer_x_cm", "engineer_y_cm",
        "infantry_3_x_cm", "infantry_3_y_cm", "infantry_4_x_cm", "infantry_4_y_cm",
        "drone_x_cm", "drone_y_cm", "sentry_x_cm", "sentry_y_cm"]]),
    0x0A02: ("opp_hp", [F(n, "H") for n in [
        "hero_1_hp", "engineer_2_hp", "infantry_3_hp", "infantry_4_hp", "reserved", "sentry_7_hp"]]),
    0x0A03: ("opp_projectiles", [F(n, "H") for n in [
        "hero_1_allowance", "infantry_3_allowance", "infantry_4_allowance",
        "drone_6_allowance", "sentry_7_allowance"]]),
    0x0A04: ("opp_macro_status", [F("remaining_gold", "H"), F("total_gold", "H"), F("status", "I", [
        ("supply_zone", 0, 1), ("central_highland", 1, 2), ("trapezoid_highland", 3, 1),
        ("fortress_buff", 4, 2), ("outpost_buff", 6, 2), ("base_buff", 8, 1),
        ("tunnel_opp_before_slope", 9, 1), ("tunnel_opp_after_slope", 10, 1),
        ("tunnel_own_before_slope", 11, 1), ("tunnel_own_after_slope", 12, 1),
        ("opp_highland_card", 13, 1), ("opp_ramp_card", 14, 1), ("opp_road_card", 15, 1)])]),
    0x0A05: ("opp_buffs", buff_fields("hero_") + buff_fields("engineer_") + buff_fields("infantry_3_")
             + buff_fields("infantry_4_") + buff_fields("sentry_") + [F("sentry_posture", "B")]),
    0x0A06: ("opp_interference_key", [F("key", "a6")]),
}

SUB_COMMANDS = {
    0x0100: ("layer_delete", [F("delete_type", "B"), F("layer", "B")]),
    0x0101: ("draw_1_figure", figure_fields(1)),
    0x0102: ("draw_2_figures", figure_fields(2)),
    0x0103: ("draw_5_figures", figure_fields(5)),
    0x0104: ("draw_7_figures", figure_fields(7)),
    0x0110: ("draw_character", figure_fields(1) + [F("text", "a30")]),
    0x0120: ("sentry_cmd", [F("sentry_cmd", "I", [
        ("confirm_respawn", 0, 1), ("confirm_instant_respawn", 1, 1),
        ("projectile_exchange_value", 2, 11), ("remote_projectile_requests", 13, 4),
        ("remote_hp_requests", 17, 4), ("mode", 21, 2), ("activate_power_rune", 23, 1)])]),
    0x0121: ("radar_cmd", [F("radar_cmd", "B"), F("password_cmd", "B"), F("password", "a6")]),
}
ROBOT_TO_ROBOT = ("robot_interaction", [F("payload", "x*")])   # sub-IDs 0x0200-0x02FF


def lookup_sub(sub_id):
    if sub_id in SUB_COMMANDS:
        return SUB_COMMANDS[sub_id]
    if 0x0200 <= sub_id <= 0x02FF:
        return ROBOT_TO_ROBOT
    return ("unknown_sub", [F("payload", "x*")])


def columns_of(fields):
    return [c for f in fields for c in f.columns()]


# ============================================================== frame parser
class RefereeParser:
    HEADER_LEN = 5
    MAX_DATA_LEN = 512

    def __init__(self):
        self.buf = bytearray()
        self.stats = {"ok": 0, "crc8_fail": 0, "crc16_fail": 0, "bad_len": 0,
                      "seq_gaps": 0, "junk_bytes": 0}
        self.last_seq = None

    def feed(self, chunk):
        """Add bytes; yield (seq, cmd_id, data, frame) for each valid frame."""
        self.buf += chunk
        while True:
            start = self.buf.find(0xA5)
            if start < 0:
                self.stats["junk_bytes"] += len(self.buf)
                self.buf.clear()
                return
            if start:
                self.stats["junk_bytes"] += start
                del self.buf[:start]
            if len(self.buf) < self.HEADER_LEN:
                return
            hdr = self.buf[:self.HEADER_LEN]
            if crc8(hdr[:4]) != hdr[4]:
                self.stats["crc8_fail"] += 1
                del self.buf[0]
                continue
            data_len = hdr[1] | (hdr[2] << 8)
            if data_len > self.MAX_DATA_LEN:
                self.stats["bad_len"] += 1
                del self.buf[0]
                continue
            frame_len = self.HEADER_LEN + 2 + data_len + 2
            if len(self.buf) < frame_len:
                return
            frame = bytes(self.buf[:frame_len])
            if crc16(frame[:-2]) != (frame[-2] | (frame[-1] << 8)):
                self.stats["crc16_fail"] += 1
                del self.buf[0]
                continue
            del self.buf[:frame_len]
            seq = hdr[3]
            if self.last_seq is not None and seq != (self.last_seq + 1) & 0xFF:
                self.stats["seq_gaps"] += 1
            self.last_seq = seq
            self.stats["ok"] += 1
            yield seq, frame[5] | (frame[6] << 8), frame[7:7 + data_len], frame


# ============================================================== CSV output
class CsvLogger:
    BASE = ["host_time", "t_s", "seq", "data_len"]

    def __init__(self, outdir):
        self.outdir = outdir
        os.makedirs(outdir, exist_ok=True)
        self.files = {}          # key -> (fh, DictWriter)
        self.t0 = time.monotonic()
        self.last_flush = 0.0
        self.counts = {}
        all_fh = open(os.path.join(outdir, "all_frames.csv"), "w", newline="")
        self.all_writer = csv.writer(all_fh)
        self.all_writer.writerow(["host_time", "t_s", "seq", "cmd_id", "name", "data_len", "frame_hex"])
        self.files["__all__"] = (all_fh, None)

    def _writer(self, key, filename, columns):
        if key not in self.files:
            fh = open(os.path.join(self.outdir, filename), "w", newline="")
            w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
            w.writeheader()
            self.files[key] = (fh, w)
        return self.files[key][1]

    def log(self, seq, cmd_id, data, frame):
        now = dt.datetime.now().isoformat(timespec="milliseconds")
        t_s = f"{time.monotonic() - self.t0:.3f}"
        base = {"host_time": now, "t_s": t_s, "seq": seq, "data_len": len(data)}

        name, fields = COMMANDS.get(cmd_id, ("unknown", [F("payload", "x*")]))
        if cmd_id == 0x0301 and len(data) >= 6:
            sub_id, sender, receiver = struct.unpack_from("<HHH", data)
            sub_name, sub_fields = lookup_sub(sub_id)
            row = {**base, "sub_id": f"0x{sub_id:04X}", "sender_id": sender,
                   "receiver_id": receiver, **decode_fields(data[6:], sub_fields)}
            cols = self.BASE + ["sub_id", "sender_id", "receiver_id"] + columns_of(sub_fields) + ["raw_hex"]
            key, fname = (cmd_id, sub_id), f"0x0301_sub_0x{sub_id:04X}_{sub_name}.csv"
            name = f"{name}/{sub_name}"
        else:
            if fields is None:   # 0x0301 shorter than its 6-byte header
                fields = [F("payload", "x*")]
            row = {**base, **decode_fields(data, fields)}
            cols = self.BASE + columns_of(fields) + ["raw_hex"]
            key, fname = cmd_id, f"0x{cmd_id:04X}_{name}.csv"
        row["raw_hex"] = data.hex()

        self._writer(key, fname, cols).writerow(row)
        self.all_writer.writerow([now, t_s, seq, f"0x{cmd_id:04X}", name, len(data), frame.hex()])
        self.counts[name] = self.counts.get(name, 0) + 1

        if time.monotonic() - self.last_flush > 0.5:
            self.flush()
        return name, row

    def flush(self):
        for fh, _ in self.files.values():
            fh.flush()
        self.last_flush = time.monotonic()

    def close(self):
        for fh, _ in self.files.values():
            fh.close()


# ============================================================== decode for display
def decode_frame(cmd_id, data):
    """Return (name, fields_spec, decoded_dict, prefix_dict)."""
    name, fields = COMMANDS.get(cmd_id, ("unknown", [F("payload", "x*")]))
    if cmd_id == 0x0301 and len(data) >= 6:
        sub_id, sender, receiver = struct.unpack_from("<HHH", data)
        sub_name, sub_fields = lookup_sub(sub_id)
        prefix = {"sub_id": f"0x{sub_id:04X}", "sender_id": sender, "receiver_id": receiver}
        return f"{name}/{sub_name}", sub_fields, decode_fields(data[6:], sub_fields), prefix
    if fields is None:
        fields = [F("payload", "x*")]
    return name, fields, decode_fields(data, fields), {}


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.4g}" if abs(v) < 1e5 else f"{v:.6g}"
    return str(v)


def pretty(fields, decoded, prefix):
    """Readable one-line summary: set single-bit flags collapsed into flags=[...]."""
    parts = [f"{k}={v}" for k, v in prefix.items()]
    set_flags = []
    for f in fields:
        if f.keep and f.name in decoded:
            v = decoded[f.name]
            if f.bits and isinstance(v, int):
                parts.append(f"{f.name}=0x{v:X}")
            else:
                parts.append(f"{f.name}={_fmt(v)}")
        for bname, _, width in f.bits:
            if bname not in decoded:
                continue
            if width == 1:
                if decoded[bname]:
                    set_flags.append(bname)
            else:
                parts.append(f"{bname}={decoded[bname]}")
    if any(f.bits and any(w == 1 for _, _, w in f.bits) for f in fields):
        parts.append("flags=[" + ",".join(set_flags) + "]")
    return "  ".join(parts)


def list_commands():
    for cmd, (name, fields) in sorted(COMMANDS.items()):
        if fields is None:
            print(f"0x{cmd:04X} {name}  (sub_id, sender_id, receiver_id + sub-content:)")
            for sub, (sname, sfields) in sorted(SUB_COMMANDS.items()):
                print(f"    sub 0x{sub:04X} {sname}: {', '.join(columns_of(sfields))}")
            print("    sub 0x0200-0x02FF robot_interaction: payload")
            continue
        print(f"0x{cmd:04X} {name}: {', '.join(columns_of(fields))}")


# ============================================================== live plot
DEFAULT_PLOT = ["0x0202.buffer_energy", "0x0202.heat_17mm", "0x0202.heat_42mm", "0x0201.current_hp"]


def run_plot(latest, stop, specs, window_s=30.0):
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation

    series = []
    for s in specs:
        cmd, field = s.split(".", 1)
        series.append((s, int(cmd, 0), field))
    hist = {s: collections.deque() for s, _, _ in series}
    last_ts = {s: 0.0 for s, _, _ in series}
    t0 = time.time()

    fig, axes = plt.subplots(len(series), 1, sharex=True, figsize=(9, 2 + 1.6 * len(series)),
                             squeeze=False)
    axes = axes[:, 0]
    lines = {}
    for ax, (label, _, _) in zip(axes, series):
        (lines[label],) = ax.plot([], [], lw=1.5)
        ax.set_ylabel(label, fontsize=8)
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("time (s)")
    fig.suptitle("Referee system live data")

    def update(_):
        now = time.time() - t0
        for label, cmd, field in series:
            entry = latest.get(cmd)
            if entry and entry[0] != last_ts[label] and isinstance(entry[1].get(field), (int, float)):
                last_ts[label] = entry[0]
                hist[label].append((entry[0] - t0, entry[1][field]))
            while hist[label] and hist[label][0][0] < now - window_s:
                hist[label].popleft()
            if hist[label]:
                xs, ys = zip(*hist[label])
                lines[label].set_data(xs, ys)
        for ax in axes:
            ax.set_xlim(max(0, now - window_s), max(window_s, now))
            ax.relim()
            ax.autoscale_view(scalex=False)
        return list(lines.values())

    _ani = animation.FuncAnimation(fig, update, interval=100, cache_frame_data=False)
    plt.show()
    stop.set()


# ============================================================== main
def reader_loop(source, parser, args, latest, stop, logger, raw_fh):
    only = {int(x, 0) for x in args.only} if args.only else None
    skip = {int(x, 0) for x in args.skip} if args.skip else set()
    last_stats = time.monotonic()
    for chunk in source:
        if stop.is_set():
            break
        if not chunk:
            continue
        if raw_fh:
            raw_fh.write(chunk)
        for seq, cmd_id, data, frame in parser.feed(chunk):
            if logger:
                logger.log(seq, cmd_id, data, frame)
            name, fields, decoded, prefix = decode_frame(cmd_id, data)
            latest[cmd_id] = (time.time(), decoded)
            if (only and cmd_id not in only) or cmd_id in skip or args.quiet:
                continue
            t = time.strftime("%H:%M:%S")
            print(f"[{t}] seq={seq:3d} cmd=0x{cmd_id:04X} len={len(data):3d} {name:22s} "
                  + pretty(fields, decoded, prefix), flush=True)
            if args.raw:
                print(f"    raw: {frame.hex(' ')}")
        if args.stats_every and time.monotonic() - last_stats > args.stats_every:
            print(f"--- stats: {parser.stats}", file=sys.stderr)
            last_stats = time.monotonic()
    stop.set()


def main():
    ap = argparse.ArgumentParser(description="RoboMaster referee parser (all commands)")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0")
    ap.add_argument("-b", "--baud", type=int, default=115200,
                    help="115200 standard link, 921600 VTM link")
    ap.add_argument("--only", nargs="+", metavar="CMD", help="only print these cmd_ids, e.g. 0x0202")
    ap.add_argument("--skip", nargs="+", metavar="CMD", help="don't print these cmd_ids")
    ap.add_argument("--raw", action="store_true", help="also print raw frame hex")
    ap.add_argument("--quiet", action="store_true", help="print nothing per frame (use with --csv)")
    ap.add_argument("--csv", action="store_true", help="log every command to CSV files")
    ap.add_argument("-o", "--outdir", default=None, help="CSV folder (default logs/referee_<timestamp>)")
    ap.add_argument("--save-raw", action="store_true", help="save raw bytes to <outdir>/raw.bin")
    ap.add_argument("--plot", nargs="*", metavar="CMD.FIELD",
                    help=f"live plot; default {' '.join(DEFAULT_PLOT)}")
    ap.add_argument("--replay", metavar="FILE", help="decode a raw capture instead of the serial port")
    ap.add_argument("--list", action="store_true", help="list all commands and fields, then exit")
    ap.add_argument("--stats-every", type=float, default=5.0, help="seconds between stats (0=off)")
    args = ap.parse_args()

    if args.list:
        list_commands()
        return

    logger = raw_fh = None
    if args.csv or args.save_raw:
        outdir = args.outdir or os.path.join(
            "logs", "referee_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
        os.makedirs(outdir, exist_ok=True)
        if args.csv:
            logger = CsvLogger(outdir)
        if args.save_raw:
            raw_fh = open(os.path.join(outdir, "raw.bin"), "wb")
        print(f"logging to {outdir}/", file=sys.stderr)

    ser = None
    if args.replay:
        def source_gen():
            with open(args.replay, "rb") as fh:
                while True:
                    c = fh.read(4096)
                    if not c:
                        return
                    yield c
    else:
        import serial
        ser = serial.Serial(args.port, args.baud, bytesize=8, parity="N", stopbits=1, timeout=0.1)

        def source_gen():
            while True:
                yield ser.read(ser.in_waiting or 1)

    parser = RefereeParser()
    latest, stop = {}, threading.Event()
    th = threading.Thread(target=reader_loop,
                          args=(source_gen(), parser, args, latest, stop, logger, raw_fh), daemon=True)
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
        if ser:
            ser.close()
        if logger:
            logger.close()
        if raw_fh:
            raw_fh.close()
        print(f"\nfinal stats: {parser.stats}", file=sys.stderr)


if __name__ == "__main__":
    main()