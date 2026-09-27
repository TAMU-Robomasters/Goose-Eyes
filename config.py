DEBUG = False
SHOW_ICON_FILTERS = False

ENEMY_COLOR = 'RED'

# cam params - SVPro global shutter camera
SOURCE = "USB_CAM" # 'REALSENSE' 'USB_CAM' or video path
#ZOOM_MODE = "10m" # TODO: determines what calibration preset to use "WIDE" "5m" "7m" "10m"

# Communication stuff
SERIAL_PORT: str = "/dev/ttyTHS1"
BAUDRATE: int = 115200

cam_width = 1280
cam_height = 720
cam_fps = 90
cam_exposure = 35

# image processing
blue_thresh = (200, 240)
red_thresh = (200, 240)

# light detection
angle_diff_multiplier = 1
misalignment_multiplier = 2
expected_distance_multiplier = 0.5
height_ratio_multiplier = 1

angle_diff_thresh = 45
misalignment_thresh = 30
height_ratio_thresh = (0.5, 2.0)
score_thresh = 200

# icon detection
icon_adaptive_thresh = (101, -5)
icon_tolerance = 40

