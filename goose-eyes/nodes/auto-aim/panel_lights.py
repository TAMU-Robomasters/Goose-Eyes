import sys
from pathlib import Path

import cv2 as cv

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from frame_processing import frame_process  # noqa: E402


def main():
	"""Capture camera frames and display contours detected in red."""
	cap = cv.VideoCapture(0)
	if not cap.isOpened():
		print("error: camera didn't open")
		return

	try:
		while True:
			success, frame = cap.read()
			if not success:
				print("error: couldn't read camera frame")
				break

			contours = frame_process(frame)
			preview = frame.copy()
			cv.drawContours(preview, contours, -1, (0, 255, 0), 2)

			for contour in contours:
				x, y, width, height = cv.boundingRect(contour)
				cv.rectangle(preview, (x, y), (x + width, y + height), (255, 0, 0), 1)

			cv.putText(
				preview,
				f"Red contours: {len(contours)}",
				(10, 30),
				cv.FONT_HERSHEY_SIMPLEX,
				0.8,
				(0, 255, 0),
				2,
			)
			cv.imshow("Red rectangle contours (press q to quit)", preview)

			if cv.waitKey(1) & 0xFF == ord("q"):
				break
	finally:
		cap.release()
		cv.destroyAllWindows()


if __name__ == "__main__":
	main()
