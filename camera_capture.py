import sys
import time

import cv2
import pyarrow as pa
from dora import Node

cap = cv2.VideoCapture(2)

if not cap.isOpened():
    print("error: camera didn't open")
    sys.exit()

node = Node()

while True:
    ret, frame = cap.read()
    if not ret:
        print("error")
        break
    frame = cv2.resize(frame, (640, 480))
    image = pa.array(frame.ravel())
    metadata = {"shape": frame.shape, "time": time.time()}

    node.send_output("image", image, metadata=metadata)
    cv2.imshow("camera capture node", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
