import cv2
from dora import Node

node = Node()
for event in node:
    if event["type"] == "INPUT":
        md = event["metadata"]
        shape = md["shape"]
        image_raveled = event["value"].to_numpy()
        image = image_raveled.reshape(shape)
        cv2.imshow("second", image)
        cv2.waitKey(1)
    elif event["type"] == "STOP":
        break

cv2.destroyAllWindows()
