import cv2 as cv
import numpy as np
import config

ENEMY_COLOR = config.ENEMY_COLOR

def frame_process(frame):
    """
    function will split color channels, threshold, and find contours.
    :param frame: input frame
    :return: contours
    """

    if (ENEMY_COLOR == 'BLUE'):
        _, thresh = cv.threshold(frame[:,:,0], config.blue_thresh[0], config.blue_thresh[1], cv.THRESH_BINARY) # tune before match
    elif (ENEMY_COLOR == 'RED'):
        _, thresh = cv.threshold(frame[:,:,2], config.red_thresh[0], config.red_thresh[1], cv.THRESH_BINARY) # tune before match
    else:
        print('invalid color')
        return []

    kernel = np.ones((3,3), np.uint8)
    closing = cv.morphologyEx(thresh, cv.MORPH_CLOSE, kernel)

    contours, _ = cv.findContours(closing, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)

    return contours
def main():
    cap = cv.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Could not open camera")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            contours = frame_process(frame)
            cv.imshow("panellight", frame)

            overlay = frame.copy()
            cv.drawContours(overlay, contours, -1, (0, 0, 255), 2)
            cv.imshow("contours", overlay)

            if cv.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv.destroyAllWindows()


if __name__ == "__main__":
    main()
