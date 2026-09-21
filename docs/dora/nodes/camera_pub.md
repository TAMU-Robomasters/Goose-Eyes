# `camera_pub`

`goose-eyes/nodes/camera_pub.py` — the source node: reads a webcam with OpenCV, resizes to 640×480,
publishes each frame and shows it in a preview window. `q` in that window stops it. Runs as `camera`
in `dataflow.yml`.

## Inputs

None.

## Outputs

| output | type | metadata | rate |
|---|---|---|---|
| `image` | `pa.array(uint8)`, flattened BGR frame (`480*640*3`) | `shape: (480, 640, 3)`, `time: float` (`time.time()` at capture) | camera-limited (typically 30 fps). TODO: measure on the Jetson |

Camera index is hard-coded (`cv2.VideoCapture(0)`, usually the built-in webcam); change it if you get
`error: camera didn't open`.
