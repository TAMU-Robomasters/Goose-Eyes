"""Dora node: append every referee message received on `referee` to a JSON-lines file."""

import json
import os
import time

from dora import Node

node = Node()
path = os.environ.get("REF_LOG", "referee_log.jsonl")

with open(path, "a") as out:
    for event in node:
        if event["type"] == "INPUT":
            md = event["metadata"]
            row = {
                "t": time.time(),
                "cmd_id": md["cmd_id"],
                "name": md["name"],
                "length_ok": md["length_ok"],
                "values": event["value"].to_pylist()[0],
            }
            out.write(json.dumps(row, default=str) + "\n")
            out.flush()
        elif event["type"] == "STOP":
            break
