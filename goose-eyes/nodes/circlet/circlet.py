import cv2
import numpy as np
from dora import Node

def getYawValueLeft(frame):
    # camera origin is in top left, so calculate x position of center of camera (we only care about x position for circlet)
    center_x = 1280/2
    # process camera feed to detect red
    difference = cv2.subtract(frame[:, :, 2], frame[:, :, 0])
    mask = cv2.inRange(difference, 70, 255)
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # array of bounding box centers
    rect_centers = []
    for contour in contours:
        rect = cv2.minAreaRect(contour)
        rect_centers.append(rect[0][0]) # append center of bounding box i
    max_cx = max(rect_centers) - center_x # turn the bounding box center values into a centered (pixel, pixel) position
    cx_to_fov = lambda cx: (120/1280) * cx # function that translates (pixel, pixel) into a degree value
    return -cx_to_fov(max_cx) - 120 # return the (pixel,pixel) position after it's translated into a yaw value for the turret to move

def getYawValueRight(frame):
    center_x = 1280/2
    difference = cv2.subtract(frame[:, :, 2], frame[:, :, 0])
    mask = cv2.inRange(difference, 70, 255)
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rect_centers = []
    for contour in contours:
        rect = cv2.minAreaRect(contour)
        rect_centers.append(rect[0][0])
    max_cx = center_x - min(rect_centers)
    cx_to_fov = lambda cx: (120/1280) * cx
    return cx_to_fov(max_cx) + 120

camera = cv2.VideoCapture(4, cv2.CAP_V4L2)
camera2 = cv2.VideoCapture(6, cv2.CAP_V4L2)
if not camera.isOpened() or not camera2.isOpened():
    raise RuntimeError("Could not open camera")

# Request the camera's 1280x720 MJPEG 90 FPS mode.
camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
camera2.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
camera.set(cv2.CAP_PROP_FPS, 90)
camera2.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
camera2.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
camera2.set(cv2.CAP_PROP_FPS, 90)

node = Node()

circlet_active = False

for event in node:
    if event["type"] == "INPUT" and event["id"] == "auto-aim-locked":
        circlet_active = bool(event["value"].to_numpy()[0])

    if not circlet_active:
        continue

    ret, frame = camera.read()
    ret2, frame2 = camera2.read()

    try:
        print(f"left: {getYawValueLeft(frame)}", end=' ')
    except Exception:
        print("error", end=' ')
    try:
        print(f"right: {getYawValueRight(frame2)}")
    except Exception:
        print("error")

camera.release()
camera2.release()
