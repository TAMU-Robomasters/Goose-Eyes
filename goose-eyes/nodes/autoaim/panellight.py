import config
import cv2 as cv
import numpy as np

ENEMY_COLOR = config.ENEMY_COLOR


def frame_process(frame):
    """
    function will isolate the enemy color in HSV, clean up the mask, and find contours.
    :param frame: input frame
    :return: contours, mask
    """
    hsv = cv.cvtColor(frame, cv.COLOR_BGR2HSV)

    if ENEMY_COLOR == "RED":
        # red wraps around hue 0, so combine both ends of the hue range
        mask1 = cv.inRange(hsv, config.red_lower1, config.red_upper1)
        mask2 = cv.inRange(hsv, config.red_lower2, config.red_upper2)
        mask = cv.bitwise_or(mask1, mask2)
    elif ENEMY_COLOR == "BLUE":
        mask = cv.inRange(hsv, config.blue_lower, config.blue_upper)
    else:
        print("invalid color")
        return [], np.zeros(frame.shape[:2], dtype=np.uint8)

    kernel = np.ones((3, 3), np.uint8)
    closing = cv.morphologyEx(mask, cv.MORPH_CLOSE, kernel)

    contours, _ = cv.findContours(closing, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)

    return contours, closing


def main():
    cap = cv.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Could not open camera")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            contours, mask = frame_process(frame)
            cv.imshow("panellight", frame)

            overlay = frame.copy()
            cv.drawContours(overlay, contours, -1, (0, 0, 255), 2)
            cv.imshow("contours", overlay)

            cv.imshow("mask", mask)

            if cv.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv.destroyAllWindows()


if __name__ == "__main__":
    main()
