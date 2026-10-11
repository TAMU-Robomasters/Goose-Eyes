import cv2
import numpy as np
from dora import Node

node = Node()

current_frame = None
current_bboxes = np.empty((0, 4), dtype=np.int32)

for event in node:
    if event["type"] == "INPUT":

        if event["id"] == "image":
            md = event["metadata"]
            shape = md["shape"]
            image_raveled = event["value"].to_numpy()
            current_frame = image_raveled.reshape(shape)

        elif event["id"] == "points":
            count = event["metadata"]["count"]
            if count > 0:
                current_bboxes = event["value"].to_numpy().reshape(count, 4)
            else:
                current_bboxes = np.empty((0, 4), dtype=np.int32)

        if current_frame is not None:
            display = current_frame.copy()

            for x, y, w, h in current_bboxes:
                cv2.rectangle(display, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(
                    display,
                    "target",
                    (x, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1,
                )

            cv2.imshow("second", display)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    elif event["type"] == "STOP":
        break

cv2.destroyAllWindows()