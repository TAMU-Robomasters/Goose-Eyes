import rerun as rr
from dora import Node

node = Node() 
rr.init("camera_test", spawn=True)

for event in node:
    if event["type"] == "INPUT":
        md = event["metadata"]
        shape = md["shape"]
        pub_time = md["time"]
        image_raveled = event["value"].to_numpy()
        image = image_raveled.reshape(shape)
        rr.log("image", rr.Image(image, color_model="BGR"))
        rr.set_time("main", duration=pub_time)
    elif event["type"] == "STOP":
        break


