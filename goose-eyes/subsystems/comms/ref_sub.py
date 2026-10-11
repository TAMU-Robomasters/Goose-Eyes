"""Dora node: print every referee message received on `referee`."""

from dora import Node

node = Node()
for event in node:
    if event["type"] == "INPUT":
        md = event["metadata"]
        values = event["value"].to_pylist()[0]
        warn = "" if md["length_ok"] else " !len"
        print(f"0x{md['cmd_id']:04X} {md['name']}{warn} {values}", flush=True)
    elif event["type"] == "STOP":
        break
