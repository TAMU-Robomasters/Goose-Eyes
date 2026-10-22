import sys
import time

import cv2 as cv
import numpy as np
import pyarrow as pa
from dora import Node

import config

ENEMY_COLOR = config.ENEMY_COLOR


def frame_process(frame: np.ndarray) -> list:
    '''
    Process a camera frame to detect lights of the enemy color.

    Args:
        frame (np.ndarray): The input camera frame.

    Returns:
        list: A list of detected lights, each represented by four corner coordinates.
    '''
    if ENEMY_COLOR == "RED":
        difference = cv.subtract(frame[:, :, 2], frame[:, :, 0])
        mask = cv.inRange(
            difference,
            config.red_lower,
            config.red_upper,
        )

    elif ENEMY_COLOR == "BLUE":
        difference = cv.subtract(frame[:, :, 0], frame[:, :, 2])
        mask = cv.inRange(
            difference,
            config.blue_lower,
            config.blue_upper,
        )

    else:
        print("Invalid enemy color:", ENEMY_COLOR)
        return []

    kernel = np.ones((3, 3), np.uint8)
    closing = cv.morphologyEx(mask, cv.MORPH_CLOSE, kernel)

    contours, _ = cv.findContours(
        closing,
        cv.RETR_TREE,
        cv.CHAIN_APPROX_SIMPLE,
    )

    light_list = []

    for contour in contours:
        if cv.contourArea(contour) <= 100:
            continue

        # Rotated rectangle around this contour.
        rect = cv.minAreaRect(contour)

        # Shape: (4, 2), containing four [x, y] corner coordinates.
        corners = cv.boxPoints(rect).astype(np.int32)

        # Store as regular Python lists for Arrow.
        light_list.append(corners.tolist())

    return light_list


def main():
    cap = cv.VideoCapture(0, cv.CAP_V4L2)

    if not cap.isOpened():
        raise RuntimeError("Could not open camera")

    cap.set(
        cv.CAP_PROP_FOURCC,
        cv.VideoWriter_fourcc(*"MJPG"),
    )
    cap.set(cv.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv.CAP_PROP_FPS, 90)

    node = Node()
    frame_id = 0

    try:
        while True:
            success, frame = cap.read()

            if not success:
                print("Could not read camera frame")
                break

            # Detection is performed on THIS exact captured frame.
            light_list = frame_process(frame)

            timestamp = time.time()

            # Both outputs carry the same ID and timestamp.
            common_metadata = {
                "frame_id": frame_id,
                "time": timestamp,
            }

            image_metadata = {
                **common_metadata,
                "shape": frame.shape,
            }

            points_metadata = {
                **common_metadata,
                "shape": (len(light_list), 4, 2),
            }

            # Image shape is (height, width, channels).
            image_output = pa.array(frame.ravel())

            # Python-equivalent form:
            # [
            #   [[x1, y1], [x2, y2], [x3, y3], [x4, y4]],
            #   ...
            # ]
            points_output = pa.array(
                light_list,
                type=pa.list_(
                    pa.list_(pa.int32(), 2),  # each corner: [x, y]
                    4,                         # four corners per light
                ),
            )

            node.send_output(
                "image",
                image_output,
                metadata=image_metadata,
            )

            node.send_output(
                "points",
                points_output,
                metadata=points_metadata,
            )

            frame_id += 1

    finally:
        cap.release()
        cv.destroyAllWindows()


if __name__ == "__main__":
    main()