from dora import Node
import pyarrow as pa

node = Node()

import time

while True:
    node.send_output(
        "auto-aim-locked", pa.array([False], type=pa.bool_())
    )
    time.sleep(0.1)