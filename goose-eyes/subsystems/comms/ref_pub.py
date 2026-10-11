"""Dora node: publish every decoded referee message as a struct on `referee`."""

import os

import pyarrow as pa
import serial
from dora import Node
from ref_comms import read_messages



def cmd_ids(name: str) -> set[int]:
    """Parse a comma/space separated env var of cmd_ids (hex or decimal) into a set."""
    return {int(tok, 0) for tok in os.environ.get(name, "").replace(",", " ").split()}


node = Node()
port = os.environ.get("REF_PORT", "/dev/ttyUSB0")
baud = int(os.environ.get("REF_BAUD", "115200"))
only = cmd_ids("REF_ONLY")  # empty = publish everything
skip = cmd_ids("REF_SKIP")

try:
    for msg in read_messages(port, baud):
        if (only and msg.cmd_id not in only) or msg.cmd_id in skip:
            continue
        node.send_output(
            "referee",
            pa.array([msg.values]),
            metadata={"cmd_id": msg.cmd_id, "name": msg.name, "length_ok": msg.length_ok},
        )
except serial.SerialException as e:
    print(e)
