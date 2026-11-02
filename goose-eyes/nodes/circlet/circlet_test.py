from dora import Node
import pyarrow as pa

node = Node()

while True:
    # # user_in = input("Is Auto-Aim on? (0 for false, 1 for true): ").strip()
    # user_in = False
    # # if user_in not in ("0", "1"):
    # #     print("Invalid input. Enter 0 or 1.")
    # #     continue

    # auto_aim = user_in == "1"

    node.send_output(
        "auto-aim-locked",pa.array([False], type=pa.bool_())
    )