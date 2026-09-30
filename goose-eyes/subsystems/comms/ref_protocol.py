"""
RoboMaster 2026 referee system payload layouts and decoding (Series Communication Protocol V1.1.0 (2025-12-30)).

Decodes each command into a flat dict of named values: 0x0001-0x020E, 0x0301 (+ sub-content IDs),
0x0302-0x0310, 0x0F01/0x0F02 and 0x0A01-0x0A06; unknown cmd_ids decode to a raw hex.
"""

import struct
from collections.abc import Sequence
from dataclasses import dataclass, field

type Value = int | float | str
type Bits = Sequence[tuple[str, int, int]]
type Layout = Sequence[Field]


# ========================= Field Specs =========================
@dataclass(frozen=True)
class Field:
    """One field of a packed little-endian struct.

    fmt: struct char(s) ('B', 'H', 'I', 'Q', 'b', 'h', 'f', '49b', ...) or custom:
         'aN' ASCII string of N bytes, 'uN' UTF-16LE text of N bytes,
         'xN' N bytes as hex, 'x*' all remaining bytes as hex.
    bits: (name, lo_bit, width) sub-fields extracted from the integer value.
    keep: False = only emit the bit fields, not the raw integer.
    """

    name: str
    fmt: str
    bits: Bits = ()
    keep: bool = True

    def columns(self) -> list[str]:
        return ([self.name] if self.keep else []) + [b[0] for b in self.bits]

    def size(self, remaining: int) -> int:
        kind = self.fmt[0]
        if self.fmt == "x*":
            return remaining
        if kind in "au" or (kind == "x" and self.fmt[1:].isdigit()):
            return int(self.fmt[1:])
        return struct.calcsize("<" + self.fmt)

    def decode(self, raw: bytes) -> dict[str, Value]:
        kind = self.fmt[0]
        if kind == "a":
            val = raw.split(b"\0")[0].decode("ascii", "replace")
        elif kind == "u":
            val = raw.decode("utf-16-le", "replace").split("\0")[0]
        elif kind == "x":
            val = raw.hex()
        else:
            vals = struct.unpack("<" + self.fmt, raw)
            val = vals[0] if len(vals) == 1 else " ".join(str(v) for v in vals)
        out = {self.name: val} if self.keep else {}
        for name, lo, width in self.bits:
            out[name] = (val >> lo) & ((1 << width) - 1)
        return out


def flags(names: Sequence[str], start: int = 0) -> Bits:
    """Single-bit flags starting at bit `start`."""
    return tuple((n, start + i, 1) for i, n in enumerate(names))


def columns_of(fields: Layout) -> list[str]:
    return [c for f in fields for c in f.columns()]


def decode_fields(data: bytes, fields: Layout) -> tuple[dict[str, Value], int, bool]:
    """Decode as many fields as `data` holds.

    Returns (values, bytes consumed, whether every field fit).
    """
    out, off = {}, 0
    for f in fields:
        n = f.size(len(data) - off)
        if off + n > len(data):
            return out, off, False
        out.update(f.decode(data[off : off + n]))
        off += n
    return out, off, True


# ========================= Command Tables =========================
# Bit-field names paraphrase the descriptions in the protocol tables.

CMD_ROBOT_INTERACTION = 0x0301
INTERACTION_HEADER = (
    Field("sub_id", "H"),
    Field("sender_id", "H"),
    Field("receiver_id", "H"),
)
RAW_PAYLOAD = (Field("payload", "x*"),)

RFID_BITS = flags(
    [
        "own_base",
        "own_central_highland",
        "opp_central_highland",
        "own_trapezoid_highland",
        "opp_trapezoid_highland",
        "own_ramp_before",
        "own_ramp_after",
        "opp_ramp_before",
        "opp_ramp_after",
        "own_cross_trapezoid_below",
        "own_cross_central_above",
        "opp_cross_central_below",
        "opp_cross_central_above",
        "own_road_below",
        "own_road_above",
        "opp_road_below",
        "opp_road_above",
        "own_fortress",
        "own_outpost",
        "own_resupply_nonoverlap",
        "own_resupply_overlap",
        "own_assembly",
        "opp_assembly",
        "central_buff_rmul",
        "opp_fortress",
        "opp_outpost",
        "own_tunnel_road_low",
        "own_tunnel_road_high",
        "own_tunnel_trapezoid_low",
        "own_tunnel_trapezoid_high",
        "opp_tunnel_road_low",
        "opp_tunnel_road_high",
    ]
)

KEY_BITS = flags(
    [
        "key_" + k
        for k in [
            "W",
            "S",
            "A",
            "D",
            "Shift",
            "Ctrl",
            "Q",
            "E",
            "R",
            "F",
            "G",
            "Z",
            "X",
            "C",
            "V",
            "B",
        ]
    ]
)


def buff_fields(prefix: str) -> list[Field]:
    return [
        Field(f"{prefix}recovery_buff", "B"),
        Field(f"{prefix}cooling_buff", "H"),
        Field(f"{prefix}defense_buff", "B"),
        Field(f"{prefix}vulnerability_buff", "B"),
        Field(f"{prefix}attack_buff", "H"),
    ]


def figure_fields(n: int) -> list[Field]:
    out = []
    for i in range(n):
        p = f"fig{i}_" if n > 1 else ""
        out += [
            Field(f"{p}name", "a3"),
            Field(
                f"{p}w1",
                "I",
                [
                    (f"{p}operate_type", 0, 3),
                    (f"{p}figure_type", 3, 3),
                    (f"{p}layer", 6, 4),
                    (f"{p}color", 10, 4),
                    (f"{p}details_a", 14, 9),
                    (f"{p}details_b", 23, 9),
                ],
                keep=False,
            ),
            Field(
                f"{p}w2",
                "I",
                [
                    (f"{p}width", 0, 10),
                    (f"{p}start_x", 10, 11),
                    (f"{p}start_y", 21, 11),
                ],
                keep=False,
            ),
            Field(
                f"{p}w3",
                "I",
                [
                    (f"{p}details_c", 0, 10),
                    (f"{p}details_d", 10, 11),
                    (f"{p}details_e", 21, 11),
                ],
                keep=False,
            ),
        ]
    return out


COMMANDS: dict[int, tuple[str, Layout]] = {
    0x0001: (
        "game_status",
        [
            Field(
                "game_type_progress",
                "B",
                [("game_type", 0, 4), ("game_progress", 4, 4)],
                keep=False,
            ),
            Field("stage_remain_time", "H"),
            Field("sync_timestamp", "Q"),
        ],
    ),
    0x0002: ("game_result", [Field("winner", "B")]),
    0x0003: (
        "game_robot_hp",
        [
            Field(n, "H")
            for n in [
                "hero_1_hp",
                "engineer_2_hp",
                "infantry_3_hp",
                "infantry_4_hp",
                "reserved",
                "sentry_7_hp",
                "outpost_hp",
                "base_hp",
            ]
        ],
    ),
    0x0101: (
        "event_data",
        [
            Field(
                "event_data",
                "I",
                [
                    ("resupply_nonoverlap_occupied", 0, 1),
                    ("resupply_overlap_occupied", 1, 1),
                    ("resupply_rmul_occupied", 2, 1),
                    ("small_rune_status", 3, 2),
                    ("large_rune_status", 5, 2),
                    ("central_highland_status", 7, 2),
                    ("trapezoid_highland_status", 9, 2),
                    ("opp_dart_last_hit_time", 11, 9),
                    ("opp_dart_last_hit_target", 20, 3),
                    ("central_buff_rmul_status", 23, 2),
                    ("fortress_buff_status", 25, 2),
                    ("outpost_buff_status", 27, 2),
                    ("base_buff_occupied", 29, 1),
                ],
            )
        ],
    ),
    0x0104: (
        "referee_warning",
        [Field("level", "B"), Field("offending_robot_id", "B"), Field("count", "B")],
    ),
    0x0105: (
        "dart_info",
        [
            Field("dart_remaining_time", "B"),
            Field(
                "dart_info",
                "H",
                [
                    ("own_dart_last_target", 0, 3),
                    ("opp_hit_count", 3, 3),
                    ("selected_target", 6, 2),
                ],
            ),
        ],
    ),
    0x0201: (
        "robot_status",
        [
            Field("robot_id", "B"),
            Field("robot_level", "B"),
            Field("current_hp", "H"),
            Field("maximum_hp", "H"),
            Field("barrel_cooling_value", "H"),
            Field("barrel_heat_limit", "H"),
            Field("chassis_power_limit", "H"),
            Field(
                "power_output",
                "B",
                flags(["gimbal_output", "chassis_output", "shooter_output"]),
            ),
        ],
    ),
    0x0202: (
        "power_heat",
        [
            Field("reserved_0", "H"),
            Field("reserved_1", "H"),
            Field("reserved_2", "f"),
            Field("buffer_energy", "H"),
            Field("heat_17mm", "H"),
            Field("heat_42mm", "H"),
        ],
    ),
    # Real referee sends 12 bytes (Table 1-13); the 16 in Table 1-4 is a doc error.
    0x0203: (
        "robot_pos",
        [Field("x_m", "f"), Field("y_m", "f"), Field("angle_deg", "f")],
    ),
    0x0204: (
        "buff",
        buff_fields("")
        + [
            Field(
                "remaining_energy",
                "B",
                flags(
                    [
                        "energy_ge_125",
                        "energy_ge_100",
                        "energy_ge_50",
                        "energy_ge_30",
                        "energy_ge_15",
                        "energy_ge_5",
                        "energy_ge_1",
                    ]
                ),
            )
        ],
    ),
    0x0206: (
        "hurt_data",
        [
            Field(
                "hurt",
                "B",
                [("armor_id", 0, 4), ("hp_deduction_reason", 4, 4)],
                keep=False,
            )
        ],
    ),
    0x0207: (
        "shoot_data",
        [
            Field("projectile_type", "B"),
            Field("shooter_number", "B"),
            Field("launching_frequency", "B"),
            Field("projectile_speed", "f"),
        ],
    ),
    0x0208: (
        "projectile_allowance",
        [
            Field("allowance_17mm", "H"),
            Field("allowance_42mm", "H"),
            Field("remaining_gold_coin", "H"),
            Field("allowance_fortress", "H"),
        ],
    ),
    0x0209: (
        "rfid_status",
        [
            Field("rfid_status", "I", RFID_BITS),
            Field(
                "rfid_status_2",
                "B",
                flags(["opp_tunnel_trapezoid_low", "opp_tunnel_trapezoid_high"]),
            ),
        ],
    ),
    0x020A: (
        "dart_client_cmd",
        [
            Field("dart_launch_opening_status", "B"),
            Field("reserved", "B"),
            Field("target_change_time", "H"),
            Field("latest_launch_cmd_time", "H"),
        ],
    ),
    0x020B: (
        "ground_robot_position",
        [
            Field(n, "f")
            for n in [
                "hero_x",
                "hero_y",
                "engineer_x",
                "engineer_y",
                "infantry_3_x",
                "infantry_3_y",
                "infantry_4_x",
                "infantry_4_y",
                "reserved_0",
                "reserved_1",
            ]
        ],
    ),
    0x020C: (
        "radar_mark_data",
        [
            Field(
                "mark",
                "H",
                flags(
                    [
                        "opp_hero_vulnerable",
                        "opp_engineer_vulnerable",
                        "opp_infantry_3_vulnerable",
                        "opp_infantry_4_vulnerable",
                        "opp_sentry_vulnerable",
                        "own_hero_tracked",
                        "own_engineer_tracked",
                        "own_infantry_3_tracked",
                        "own_infantry_4_tracked",
                        "own_sentry_tracked",
                    ]
                ),
            )
        ],
    ),
    0x020D: (
        "sentry_info",
        [
            Field(
                "sentry_info",
                "I",
                [
                    ("exchanged_projectiles", 0, 11),
                    ("remote_projectile_exchanges", 11, 4),
                    ("remote_hp_exchanges", 15, 4),
                    ("can_free_respawn", 19, 1),
                    ("can_instant_respawn", 20, 1),
                    ("instant_respawn_cost", 21, 10),
                ],
            ),
            Field(
                "sentry_info_2",
                "H",
                [("sentry_mode", 12, 2), ("power_rune_activatable", 14, 1)],
            ),
        ],
    ),
    0x020E: (
        "radar_info",
        [
            Field(
                "radar_info",
                "B",
                [
                    ("double_vuln_chances", 0, 2),
                    ("opp_double_vuln_active", 2, 1),
                    ("own_encryption_level", 3, 2),
                    ("key_modifiable", 5, 1),
                ],
            )
        ],
    ),
    # Header only; the sub-content layout is picked from SUB_COMMANDS by sub_id.
    CMD_ROBOT_INTERACTION: ("robot_interaction", INTERACTION_HEADER),
    0x0302: ("custom_controller_data", [Field("data", "x*")]),
    0x0303: (
        "map_command",
        [
            Field("target_x", "f"),
            Field("target_y", "f"),
            Field("cmd_keyboard", "B"),
            Field("opponent_robot_id", "B"),
            Field("source_id", "H"),
        ],
    ),
    0x0304: (
        "remote_control",
        [
            Field("mouse_x", "h"),
            Field("mouse_y", "h"),
            Field("mouse_z", "h"),
            Field("left_button_down", "b"),
            Field("right_button_down", "b"),
            Field("keyboard_value", "H", KEY_BITS),
            Field("reserved", "H"),
        ],
    ),
    0x0305: (
        "map_robot_data",
        [
            Field(n, "H")
            for n in [
                "hero_x_cm",
                "hero_y_cm",
                "engineer_x_cm",
                "engineer_y_cm",
                "infantry_3_x_cm",
                "infantry_3_y_cm",
                "infantry_4_x_cm",
                "infantry_4_y_cm",
                "infantry_5_x_cm",
                "infantry_5_y_cm",
                "sentry_x_cm",
                "sentry_y_cm",
            ]
        ],
    ),
    0x0306: (
        "custom_client_data",
        [
            Field("key_value", "H", [("key_1", 0, 8), ("key_2", 8, 8)]),
            Field(
                "mouse_x_word",
                "H",
                [("mouse_x_px", 0, 12), ("mouse_left", 12, 4)],
                keep=False,
            ),
            Field(
                "mouse_y_word",
                "H",
                [("mouse_y_px", 0, 12), ("mouse_right", 12, 4)],
                keep=False,
            ),
            Field("reserved", "H"),
        ],
    ),
    0x0307: (
        "map_path_data",
        [
            Field("intention", "B"),
            Field("start_x_dm", "H"),
            Field("start_y_dm", "H"),
            Field("delta_x_dm", "49b"),
            Field("delta_y_dm", "49b"),
            Field("sender_id", "H"),
        ],
    ),
    0x0308: (
        "custom_info",
        [Field("sender_id", "H"), Field("receiver_id", "H"), Field("text", "u30")],
    ),
    0x0309: ("robot_custom_data", [Field("data", "x*")]),
    0x0310: ("robot_custom_data_2", [Field("data", "x*")]),
    0x0F01: ("vtm_set_channel", [Field("value", "B")]),
    0x0F02: ("vtm_query_channel", [Field("channel", "B")]),
    0x0A01: (
        "opp_positions",
        [
            Field(n, "H")
            for n in [
                "hero_x_cm",
                "hero_y_cm",
                "engineer_x_cm",
                "engineer_y_cm",
                "infantry_3_x_cm",
                "infantry_3_y_cm",
                "infantry_4_x_cm",
                "infantry_4_y_cm",
                "drone_x_cm",
                "drone_y_cm",
                "sentry_x_cm",
                "sentry_y_cm",
            ]
        ],
    ),
    0x0A02: (
        "opp_hp",
        [
            Field(n, "H")
            for n in [
                "hero_1_hp",
                "engineer_2_hp",
                "infantry_3_hp",
                "infantry_4_hp",
                "reserved",
                "sentry_7_hp",
            ]
        ],
    ),
    0x0A03: (
        "opp_projectiles",
        [
            Field(n, "H")
            for n in [
                "hero_1_allowance",
                "infantry_3_allowance",
                "infantry_4_allowance",
                "drone_6_allowance",
                "sentry_7_allowance",
            ]
        ],
    ),
    0x0A04: (
        "opp_macro_status",
        [
            Field("remaining_gold", "H"),
            Field("total_gold", "H"),
            Field(
                "status",
                "I",
                [
                    ("supply_zone", 0, 1),
                    ("central_highland", 1, 2),
                    ("trapezoid_highland", 3, 1),
                    ("fortress_buff", 4, 2),
                    ("outpost_buff", 6, 2),
                    ("base_buff", 8, 1),
                    ("tunnel_opp_before_slope", 9, 1),
                    ("tunnel_opp_after_slope", 10, 1),
                    ("tunnel_own_before_slope", 11, 1),
                    ("tunnel_own_after_slope", 12, 1),
                    ("opp_highland_card", 13, 1),
                    ("opp_ramp_card", 14, 1),
                    ("opp_road_card", 15, 1),
                ],
            ),
        ],
    ),
    0x0A05: (
        "opp_buffs",
        buff_fields("hero_")
        + buff_fields("engineer_")
        + buff_fields("infantry_3_")
        + buff_fields("infantry_4_")
        + buff_fields("sentry_")
        + [Field("sentry_posture", "B")],
    ),
    0x0A06: ("opp_interference_key", [Field("key", "a6")]),
}

SUB_COMMANDS: dict[int, tuple[str, Layout]] = {
    0x0100: ("layer_delete", [Field("delete_type", "B"), Field("layer", "B")]),
    0x0101: ("draw_1_figure", figure_fields(1)),
    0x0102: ("draw_2_figures", figure_fields(2)),
    0x0103: ("draw_5_figures", figure_fields(5)),
    0x0104: ("draw_7_figures", figure_fields(7)),
    0x0110: ("draw_character", figure_fields(1) + [Field("text", "a30")]),
    0x0120: (
        "sentry_cmd",
        [
            Field(
                "sentry_cmd",
                "I",
                [
                    ("confirm_respawn", 0, 1),
                    ("confirm_instant_respawn", 1, 1),
                    ("projectile_exchange_value", 2, 11),
                    ("remote_projectile_requests", 13, 4),
                    ("remote_hp_requests", 17, 4),
                    ("mode", 21, 2),
                    ("activate_power_rune", 23, 1),
                ],
            )
        ],
    ),
    0x0121: (
        "radar_cmd",
        [Field("radar_cmd", "B"), Field("password_cmd", "B"), Field("password", "a6")],
    ),
}
ROBOT_TO_ROBOT = (
    "robot_interaction",
    RAW_PAYLOAD,
)  # sub-IDs 0x0200-0x02FF, team-defined


def lookup_sub(sub_id: int) -> tuple[str, Layout]:
    if sub_id in SUB_COMMANDS:
        return SUB_COMMANDS[sub_id]
    if 0x0200 <= sub_id <= 0x02FF:
        return ROBOT_TO_ROBOT
    return ("unknown_sub", RAW_PAYLOAD)


# ========================= Decoding =========================
@dataclass(frozen=True)
class Message:
    """A decoded data segment.

    name: command name.
    values: field name -> value, in layout order.
    length_ok: False if the payload was shorter or longer than its layout. Missing trailing
        fields are left out of `values`; extra bytes are ignored.
    fields: the layout that was applied, for formatting.
    """

    cmd_id: int
    name: str
    values: dict[str, Value]
    length_ok: bool
    fields: tuple[Field, ...] = field(repr=False)


def decode(cmd_id: int, data: bytes) -> Message:
    """Decode the data segment of one frame."""
    name, fields = COMMANDS.get(cmd_id, ("unknown", RAW_PAYLOAD))
    values, used, complete = decode_fields(data, fields)
    if cmd_id == CMD_ROBOT_INTERACTION and complete:
        sub_name, sub_fields = lookup_sub(values["sub_id"])
        sub_values, sub_used, complete = decode_fields(data[used:], sub_fields)
        name = f"{name}/{sub_name}"
        fields = (*fields, *sub_fields)
        values |= sub_values
        used += sub_used
    return Message(cmd_id, name, values, complete and used == len(data), tuple(fields))
