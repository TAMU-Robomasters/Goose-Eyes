from dora import Node
import pyarrow as pa
import random

node = Node()

import time

while True:
    node.send_output(
        "auto-aim-locked", pa.array([random.choice([True, False])], type=pa.bool_())
    )
    time.sleep(random.random())