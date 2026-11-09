import pyarrow as pa
from dora import Node

node = Node()
pending = None

for event in node:
    if event["type"] != "INPUT":
        continue
    if event["id"] == "tick":
        pending = node.send_service_request("hurt_request", pa.array([0]))  # payload unused
    elif event["id"] == "response":
        if event["metadata"].get("request_id") == pending:
            print("hurt:", event["value"][0].as_py())
            pending = None