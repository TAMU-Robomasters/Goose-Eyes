import cv2
import numpy as np
from dora import Node

node = Node()

current_frame = None

# Shape: (number_of_lights, 4_corners, 2_coordinates)
current_boxes = np.empty((0, 4, 2), dtype=np.int32)

for event in node:
    if event["type"] == "INPUT":

        if event["id"] == "image":
            shape = event["metadata"]["shape"]
            image_raveled = event["value"].to_numpy()
            current_frame = image_raveled.reshape(shape)

        # Ensure this matches the output name in the dataflow.
        # Your detector calls send_output("point", ...), so it may be "point",
        # rather than "points".
        elif event["id"] == "points":
            points = event["value"].to_pylist()

            if points:
                current_boxes = np.asarray(points, dtype=np.int32).reshape(-1, 4, 2)
            else:
                current_boxes = np.empty((0, 4, 2), dtype=np.int32)

        if current_frame is not None:
            display = current_frame.copy()

            for corners in current_boxes:
                # corners has shape (4, 2):
                # [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]

                # Draw the closed rotated rectangle.
                cv2.polylines(
                    display,
                    [corners.reshape((-1, 1, 2))],
                    isClosed=True,
                    color=(0, 255, 0),
                    thickness=2,
                )

                # Optionally draw each corner and its index.
                for index, (x, y) in enumerate(corners):
                    cv2.circle(display, (int(x), int(y)), 4, (0, 0, 255), -1)
                    cv2.putText(
                        display,
                        str(index),
                        (int(x) + 5, int(y) - 5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.4,
                        (0, 255, 255),
                        1,
                    )

                # Label near the first returned corner.
                x, y = corners[0]
                cv2.putText(
                    display,
                    "target",
                    (int(x), int(y) - 8),
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