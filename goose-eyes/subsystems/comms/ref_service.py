import time

import pyarrow as pa
from dora import Node

HURT_UART = 0x0206

node = Node()
latest = None

for event in node:
    if event["type"] != "INPUT":
        continue

    if event["id"] == "referee":
        if event["metadata"].get("cmd_id") == HURT_UART:
            hurt_data = event["value"][0].as_py()
            latest = {**hurt_data, "t": time.time()}
    elif event["id"] == "hurt_request":
        if latest is None:
            reply = {"valid": False, "armor_id": 0, "hp_deduction_reason": 0, "t": 0.0}
        else:
            reply = {"valid": True, **latest}
        node.send_service_response(
            "response",
            pa.array([reply]),
            metadata=event["metadata"],  # flat, keeps request_id
        )
        