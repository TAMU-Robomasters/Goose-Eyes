import os
import sys
from pathlib import Path

import cv2 as cv
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import config


def frame_process(frame):
    """
    function will split color channels, threshold, and find contours.
    :param frame: input frame
    :return: contours
    """

    if config.ENEMY_COLOR == "BLUE":
        _, thresh = cv.threshold(
            frame[:, :, 0], config.blue_thresh[0], config.blue_thresh[1], cv.THRESH_BINARY
        )  # tune before match
    elif config.ENEMY_COLOR == "RED":
        _, thresh = cv.threshold(
            frame[:, :, 2], config.red_thresh[0], config.red_thresh[1], cv.THRESH_BINARY
        )  # tune before match
    else:
        print("invalid color")
        return []

    kernel = np.ones((3, 3), np.uint8)
    closing = cv.morphologyEx(thresh, cv.MORPH_CLOSE, kernel)
    contours, _ = cv.findContours(closing, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)

    return contours


def red_light_boxes(frame):
    """Return bounding boxes around saturated, tall red regions in a BGR frame."""
    hsv = cv.cvtColor(frame, cv.COLOR_BGR2HSV)
    min_value = config.red_thresh[0]
    lower_red = cv.inRange(hsv, np.array([0, 100, min_value]), np.array([10, 255, 255]))
    upper_red = cv.inRange(hsv, np.array([170, 100, min_value]), np.array([180, 255, 255]))
    mask = cv.bitwise_or(lower_red, upper_red)
    mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    min_height = max(12, int(frame.shape[0] * 0.025))
    boxes = []
    for contour in contours:
        x, y, width, height = cv.boundingRect(contour)
        if height >= min_height and height >= 2 * width:
            boxes.append((x, y, width, height))
    return boxes


def main():
    """Display camera 0 with bounding boxes around detected red lights."""
    cap = cv.VideoCapture(0)
    if not cap.isOpened():
        print("error: camera didn't open")
        return

    try:
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            success, frame = cap.read()
            if success:
                snapshot = Path(__file__).with_name("raw_frame.jpg")
                preview = frame.copy()
                boxes = red_light_boxes(frame)
                for x, y, width, height in boxes:
                    cv.rectangle(preview, (x, y), (x + width, y + height), (0, 255, 0), 2)
                if cv.imwrite(str(snapshot), preview):
                    print(f"No graphical display available; saved an annotated frame to {snapshot}")
                else:
                    print("error: couldn't save a raw frame")
            else:
                print("error: couldn't read camera frame")
            print("For a live preview, run from a graphical desktop or enable X11 forwarding.")
            return

        while True:
            success, frame = cap.read()
            if not success:
                print("error: couldn't read camera frame")
                break

            preview = frame.copy()
            boxes = red_light_boxes(frame)
            for x, y, width, height in boxes:
                cv.rectangle(preview, (x, y), (x + width, y + height), (0, 255, 0), 2)
            cv.putText(
                preview,
                f"Red lights: {len(boxes)}",
                (10, 30),
                cv.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
            )
            cv.imshow("Red light detection (press q to quit)", preview)
            if cv.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv.destroyAllWindows()


if __name__ == "__main__":
    main()
