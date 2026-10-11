import config
import cv2 as cv
import numpy as np
from dora import Node
import pyarrow as pa


ENEMY_COLOR = config.ENEMY_COLOR


def frame_process(frame):
    if ENEMY_COLOR == "RED":
        mask = cv.inRange(frame, config.red_lower1, config.red_upper1)
    elif ENEMY_COLOR == "BLUE":
        mask = cv.inRange(frame, config.blue_lower, config.blue_upper)
    else:
        print("invalid color")
        return [], np.zeros(frame.shape[:2], dtype=np.uint8)

    kernel = np.ones((3, 3), np.uint8)
    closing = cv.morphologyEx(mask, cv.MORPH_CLOSE, kernel)

    contours, _ = cv.findContours(closing, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)

    light_list = []
    for cnt in contours:
        area = cv.contourArea(cnt)
        if area > 100:  # filter out small contours
            light_list.append(cnt)

    return light_list, closing


node = Node()
for event in node:
    if event["type"] == "INPUT":
        md = event["metadata"]
        shape = md["shape"]
        image_raveled = event["value"].to_numpy()
        image = image_raveled.reshape(shape)
        contours, mask = frame_process(image)
        node.send_output("point", pa.array(contours))
    elif event["type"] == "STOP":
        break
