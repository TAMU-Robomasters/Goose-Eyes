import config
import cv2 as cv
import numpy as np
from dora import Node
import pyarrow as pa

ENEMY_COLOR = config.ENEMY_COLOR


def frame_process(frame):
    if ENEMY_COLOR == "RED":
        mask = cv.inRange(
            cv.subtract(frame[:, :, 2], frame[:, :, 0]),
            config.red_lower,
            config.red_upper,
        )
    elif ENEMY_COLOR == "BLUE":
        mask = cv.inRange(
            cv.subtract(frame[:, :, 0], frame[:, :, 2]),
            config.blue_lower,
            config.blue_upper,
        )
    else:
        print("invalid color")
        return [], np.zeros(frame.shape[:2], dtype=np.uint8)

    kernel = np.ones((3, 3), np.uint8)
    closing = cv.morphologyEx(mask, cv.MORPH_CLOSE, kernel)

    contours, _ = cv.findContours(
        closing,
        cv.RETR_TREE,
        cv.CHAIN_APPROX_SIMPLE,
    )

    light_list = []

    for cnt in contours:
        area = cv.contourArea(cnt)

        if area > 100:
            rect = cv.minAreaRect(cnt)
            corners = cv.boxPoints(rect)

            # Explicitly use a consistent Arrow-compatible integer type.
            corners = corners.astype(np.int32)

            # Shape: (4, 2), e.g. [[x, y], [x, y], [x, y], [x, y]]
            light_list.append(corners.tolist())

    return light_list, closing


node = Node()

for event in node:
    if event["type"] == "INPUT":
        shape = event["metadata"]["shape"]
        image_raveled = event["value"].to_numpy()
        image = image_raveled.reshape(shape)

        light_list, mask = frame_process(image)

        # Outer list: detected lights
        # Middle list: four corners per light
        # Inner list: [x, y]
        points = pa.array(
            light_list,
            type=pa.list_(
                pa.list_(pa.int32(), 2),  # one [x, y] corner
                4,                         # four corners
            ),
        )

        node.send_output("points", points)

    elif event["type"] == "STOP":
        break

cv.destroyAllWindows()