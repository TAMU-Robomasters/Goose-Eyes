import sys
import time

import cv2
import pyarrow as pa
from dora import Node

cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

if not cap.isOpened():
    raise RuntimeError("Could not open cap")

cap.set(
    cv2.CAP_PROP_FOURCC,
    cv2.VideoWriter_fourcc(*"MJPG"),
)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 90)

if not cap.isOpened():
    print("error: camera didn't open")
    sys.exit()

node = Node()

while True:
    ret, frame = cap.read()
    if not ret:
        print("error")
        break
    image = pa.array(frame.ravel())
    metadata = {"shape": frame.shape, "time": time.time()}

    node.send_output("image", image, metadata=metadata)
    cv2.imshow("camera capture node", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
