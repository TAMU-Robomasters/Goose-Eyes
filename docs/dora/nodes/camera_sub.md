# `camera_sub`

`goose-eyes/nodes/camera_sub.py` — sink that reshapes the frame from its `shape` metadata and shows it
with `cv2.imshow` (window *second*). Exits on the dataflow's `STOP` event. Runs as `displayer` in
`dataflow.yml`.

## Inputs

| input | type | metadata used | rate |
|---|---|---|---|
| `image` | `pa.array(uint8)`, flattened BGR frame | `shape` | follows [camera_pub](camera_pub.md) |

## Outputs

None.
