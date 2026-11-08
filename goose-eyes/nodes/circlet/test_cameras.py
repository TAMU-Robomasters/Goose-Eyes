import cv2
import sys

# ==========================================
# CHANGE YOUR CAMERA INDICES HERE
# ==========================================
CAMERA_1_INDEX = 0
CAMERA_2_INDEX = 4
# ==========================================

def test_cameras():
    print(f"Initializing cameras at index {CAMERA_1_INDEX} and {CAMERA_2_INDEX}...")
    camera1 = cv2.VideoCapture(CAMERA_1_INDEX, cv2.CAP_V4L2)
    camera2 = cv2.VideoCapture(CAMERA_2_INDEX, cv2.CAP_V4L2)

    if not camera1.isOpened():
        print(f"CRITICAL: Camera index {CAMERA_1_INDEX} could not be opened.")
        sys.exit(1)
    if not camera2.isOpened():
        print(f"CRITICAL: Camera index {CAMERA_2_INDEX} could not be opened.")
        sys.exit(1)

    # Configure MJPEG 90FPS at 1280x720
    for i, cam in enumerate([camera1, camera2], start=1):
        idx = CAMERA_1_INDEX if i == 1 else CAMERA_2_INDEX
        cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cam.set(cv2.CAP_PROP_FPS, 90)
        print(f"Camera {i} (Index {idx}) configured successfully.")

    print("\nPress 'q' in any video window to exit.")

    while True:
        ret1, frame1 = camera1.read()
        ret2, frame2 = camera2.read()

        if not ret1:
            print(f"Warning: Failed to grab frame from Camera 1 (Index {CAMERA_1_INDEX})")
        else:
            cv2.imshow(f"Camera 1 (Index {CAMERA_1_INDEX})", frame1)

        if not ret2:
            print(f"Warning: Failed to grab frame from Camera 2 (Index {CAMERA_2_INDEX})")
        else:
            cv2.imshow(f"Camera 2 (Index {CAMERA_2_INDEX})", frame2)

        # Break loop if 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Cleanup
    camera1.release()
    camera2.release()
    cv2.destroyAllWindows()
    print("Cameras released. Test ended safely.")

if __name__ == "__main__":
    test_cameras()
