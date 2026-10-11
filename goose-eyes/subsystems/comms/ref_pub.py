"""Dora node: publish every decoded referee message as a struct on `referee`."""

import os

import pyarrow as pa
import serial
from dora import Node
from ref_comms import read_messages

node = Node()
port = os.environ.get("REF_PORT", "/dev/ttyUSB0")
baud = int(os.environ.get("REF_BAUD", "115200"))

try:
    for msg in read_messages(port, baud):
        node.send_output(
            "referee",
            pa.array([msg.values]),
            metadata={"cmd_id": msg.cmd_id, "name": msg.name, "length_ok": msg.length_ok},
        )
except serial.SerialException as e:
    print(e)
