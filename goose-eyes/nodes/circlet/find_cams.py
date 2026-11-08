# this code will probs only work on linux

import cv2
import glob
import re

def find_all_camera_indices():
    print("Scanning system for available video devices...")
    
    # 1. Look for all video device paths in Linux (/dev/video0, /dev/video1, etc.)
    device_paths = glob.glob("/dev/video*")
    
    if not device_paths:
        print("No camera devices found in /dev/")
        return []

    # Extract just the numeric indices and sort them
    indices = sorted([int(re.search(r'\d+', path).group()) for path in device_paths])
    
    working_cameras = []

    print(f"Found hardware endpoints: {indices}")
    print("Testing OpenCV compatibility (this may take a few seconds)...")

    # 2. Test each index with OpenCV to see if it actually streams
    for index in indices:
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        if cap.isOpened():
            # Try to grab a quick frame to guarantee it's an input stream
            ret, _ = cap.read()
            if ret:
                print(f" -> [MATCH] Index {index} is a WORKING camera.")
                working_cameras.append(index)
            else:
                # Some Linux endpoints (like metadata/depth) open but don't return frames
                print(f" -> [SKIP]  Index {index} opened but returned no frames (metadata/device channel).")
            cap.release()
        else:
            pass

    print("\n==========================================")
    print(f"PROPOSED INDICES FOR YOUR CODE: {working_cameras}")
    print("==========================================")
    return working_cameras

if __name__ == "__main__":
    find_all_camera_indices()
