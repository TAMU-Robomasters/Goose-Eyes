import time

import commStructs
from gimbalSub import gimbalSub
from dora import Node

gimbalSub_obj = gimbalSub()

node = Node()

try:
    for event in node:
        if event["type"] == "INPUT":
            handle = gimbalSub_obj.setGimbal()
            if not handle:
                print("Error: could not set Gimbal!")
                continue

        elif event["type"] == "STOP":
            break

except KeyboardInterrupt:
    print("\nCtrl+C received.")
    gimbalSub_obj.comm_obj.send_query(timestamp=0, request_number=commStructs.REQUEST_RESET)
    time.sleep(0.05)

finally:
    gimbalSub_obj.closeGimbal()
    print("done")

