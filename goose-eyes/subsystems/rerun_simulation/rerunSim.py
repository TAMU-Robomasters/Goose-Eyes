import rerun as rr
import math
import numpy as np
import av
import numpy.typing as npt
from scipy.spatial.transform import Rotation as rot
import pyrealsense2 as rs
import netifaces
import random
import time
import sys

'''
CURRENT PROGRESS:
- can log video from .rrd file or from laptop video camera
- can log panels from .rrd file

MISSING:
- need to put in dora form and get ref data logged
- make the switch between the laptop video to .rrd file nicer and not involve uncommenting things
- scale the field and robots correctly
- label the panels and show their actual shape not just center position

DOCUMENTATION:
https://docs.google.com/document/d/10vgKZcUVGdw1eXas80Qi6ANJZfDAbjvqK_3WlWHjdM4/edit?tab=t.0
'''


class Simulation:
    def __init__(self, panel, frame, times) -> None:
        #show rerun simulation on your local device instead of a different one mode
        localMode = False

        #Init everything for the rerun simulation
        self.panel = panel
        self.frame = frame
        self.times = times
        rr.init("rerun_fake_data_test", spawn=False, recording_id="pleaseeework")
        rr.set_time("stable_time", duration=0)

        #Figure out if we even have real data
        if(localMode):
            panel = self.fakePanels()
            self.localVideoStreamInit()
            localIp = self.getIP()
            rr.connect_grpc(f"rerun+http://{localIp}:9876/proxy")
            rr.log("logs", rr.TextLog(f"All of this data is fake and the footage is from /dev/video0"))
            print("1simulation is going to show up on this device locally because localMode is on")
        #elif(panel is None or frame is None or len(panel) == 0 or len(frame)):
            #panel = self.fakePanels()
            #self.localVideoStreamInit()
            #rr.serve_grpc()
            #rr.log("logs", rr.TextLog(f"All of this data is fake and the footage is from /dev/video0"))
            #print("2connect to see the simulation by running: python -m rerun --connect rerun+http://ipofdeviceAfromtailscale:9876/proxy")
        else:
            #rr.log("logs", rr.TextLog(f"This should be the real data and footage... "))
            #print("connect to see the simulation by running: python -m rerun --connect rerun+http://ipofdeviceAfromtailscale:9876/proxy")
            #rr.serve_grpc()

            #panel = self.fakePanels()
            self.localVideoStreamInit()
            rr.serve_grpc()
            rr.log("logs", rr.TextLog(f"All of this data is fake and the footage is from /dev/video0"))
            print("3connect to see the simulation by running: python -m rerun --connect rerun+http://ipofdeviceAfromtailscale:9876/proxy")
        

        #Everything camera related
        #self.cameraFrameInit()
        self.pipelineInit()
        self.logCameras()

        #Main loop/updates
        self.simulate(panel, frame, times)
        time.sleep(100)

        #Exit/end of program
        print("completeee")
        rr.disconnect()

    #MAIN LOOP / UPDATES
    def simulate(self, panel, frame, times):
        #update everything else
        self.logThisRobot()
        self.logOtherRobots()
        self.logEverythingElse()

        start = times[0]

        #put live things on screen
        for p, f, t in zip(panel, frame, times):
            time.sleep(0.01)
            print("t:", t, type(t), getattr(t, "shape", None))
            print("start:", start, type(start), getattr(start, "shape", None))
            rr.set_time(
                "stable_time",
                duration=float(t-start)/1e9
            )

            #panels
            print(f"time is {t} position is {p[0]} {p[1]} {p[2]}")
            rr.log(f"markers", rr.Points3D([p]))

            #frame for camera 1 update
            rr.log("bot/cam1", rr.Image(f[0].reshape(720, 1280, 3)))

        #update camera for laptop camera not file camera
        # for f in self.input_container.decode(video=0):
        #     f.pict_type = av.video.frame.PictureType.NONE
        #     for packet in self.stream.encode(f):
        #         if packet.pts is None:
        #             continue
        #         rr.set_time("stable_time", duration=float(packet.pts * packet.time_base))
        #         for c in range(4):
        #             rr.log(f"bot/cam{c+1}", rr.VideoStream.from_fields(sample=bytes(packet)))

        # #waste some time not updating the camera and everything else
        # for i in range(400):
        #     time = i * 0.01
        #     rr.set_time("stable_time", duration=time)  

    #INIT FOR LAPTOP CAMERA PIPELINE
    def pipelineInit(self):
        av.logging.set_level(av.logging.VERBOSE)
        container = av.open("/dev/null", "w", format=self.formats[self.codec])
        self.stream = container.add_stream(self.encoders[self.codec], 
        rate=self.fps)
        assert isinstance(self.stream, av.video.stream.VideoStream)
        self.stream.bit_rate = 500000
        self.stream.width = self.width
        self.stream.height = self.height
        self.stream.pix_fmt = "yuv420p"
        self.stream.max_b_frames = 0
        print("made pipeline")

    #PLACE CAMERAS IN SIMULATION
    def logCameras(self):
        camloc = [[0, 0.25, 0.5], [0.25, 0, 0.5], [0, -0.25, 0.5], [-0.25, 0.0, 0.5]]
        camrot = [0, 270, 180, 90]
        for c in range(4):  
            quat = rot.from_euler("xz", [-90, camrot[c]], degrees=True).as_quat()
            rr.log(
                f"bot/cam{c + 1}",
                rr.Pinhole(
                    width=self.width,
                    height=self.height,
                    focal_length=self.width / 2,
                    image_plane_distance=0.2,
                ),
                rr.Transform3D(translation=camloc[c], quaternion=quat),
                static=True,
            )
            rr.log(f"bot/cam{c + 1}", rr.VideoStream(codec=self.codec), static=True)
        print("logged cams")

    #WHERE ARE THE OTHER ROBOTS
    def whereAreTheOtherRobots(self, panel):
        #  current_state.predicted_plates()[0].position(), current_state.predicted_plates()[1].position(), current_state.predicted_plates()[2].position(), current_state.predicted_plates()[3].position(),
        #             current_state.predicted_plates()[0].velocity(), current_state.predicted_plates()[1].velocity(), current_state.predicted_plates()[2].velocity(), current_state.predicted_plates()[3].velocity(),
        #             current_state.radius(), current_state.radius()))

        #get all the panel positions
        panPos = []
        pastP = panel[0].position()
        print(f"Panel {1} x: {panel[0].position()[0]} y: {panel[0].position()[1]} z: {panel[0].position()[2]}")
        for p in range(1,len(panel)):
            panPos.append(p.position())
            print(f"Panel {p+1} x: {panel[p].position()[0]} y: {panel[p].position()[1]} z: {panel[p].position()[2]}")
            dist = math.sqrt(math.pow(panel[p].position()[0]-panel[0].position()[0], 2) + math.pow(panel[p].position()[0]-panel[0].position()[0], 2) + math.pow(panel[p].position()[0]-panel[0].position()[2], 2))
        pass
        
    #LOG EVERYTHING THAT ISNT A CAMERA
    def logEverythingElse(self):
        #DECORATIONS
        rr.log(
            "world/field", 
            rr.Asset3D(path="field.stl")
        )

    def logThisRobot(self):
        rr.log(
            "bot/main",
            rr.Cylinders3D(
                lengths=0.5,
                radii=0.3,
                colors=[128, 128, 200],
                fill_mode=3,
                centers=(0, 0, 0.25),
            ),
        )
        rr.log(
            "bot",
            rr.Transform3D(translation=[2, 2, 0]),
        )
        
    def logOtherRobots(self):
        rr.log(
            "otherbot/main",
            rr.Cylinders3D(
                lengths=0.5,
                radii=0.3,
                colors=[128, 128, 200],
                fill_mode=1,
                centers=(0, 0, 0),
            ),
        )
        panloc = [
            [0, 0.15, 0.05],
            [0.15, 0, 0.05],
            [0, -0.15, 0.05],
            [-0.15, 0.0, 0.05],
        ]
        panrot = [0, 270, 180, 90]
        for c in range(4):
            quat = rot.from_euler("yz", [-90, panrot[c]], degrees=True).as_quat()
            rr.log(
                f"otherbot/pan{c + 1}",
                rr.Boxes3D(
                    centers=panloc[c],
                    half_sizes=[0.1, 0.05, 0.1],
                    quaternions=quat,
                    radii=0.02,
                    colors=[200, 128, 128],
                    fill_mode=1,
                    labels=[f"pan{c + 1}"],
                ),
                rr.Transform3D(translation=panloc[c]),
            )

        rr.log(
            "otherbot",
            rr.Transform3D(translation=[0, 0, 0.1]),
        )

    #FAKE DATA GENERATION
    def fakePanels(self):
        points = []
        for i in range(10):
            x = round(random.uniform(-2, 2), 2)
            y = round(random.uniform(-2, 2), 2)
            z = round(random.uniform(-2, 2), 2)
            points.append([x, y, z])
        return points

    #LOCAL CAMERA VIDEO STREAM
    def localVideoStreamInit(self,):      
            self.input_container = av.open("/dev/video0", format="v4l2")
            istr = self.input_container.streams.video[0]
            self.fps = 30
            self.duration_s = 4
            self.width = istr.width
            self.height = istr.height
            self.codec = rr.VideoCodec.H264
    
            self.formats = {rr.VideoCodec.H265: "hevc", rr.VideoCodec.H264: "h264"}
            self.encoders = {rr.VideoCodec.H265: "libx265", rr.VideoCodec.H264: "libx264"}
            print("found device camera")

    #GET LOCAL IP
    def getIP(self):
            #get all the ips
            types = []
            addresses = []
            interfaces = netifaces.interfaces()
            for interface in interfaces:
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_INET in addrs:
                    for addr_info in addrs[netifaces.AF_INET]:
                        address = addr_info['addr']
                        print(f"{interface}: {address}")
                        types.append(interface)
                        addresses.append(address)
    
            index= types.index("wlp0s20f3")
            return addresses[index]

def readDat():
    panels = []
    frame = []

    with rr.server.Server(datasets={"recording": ["fakeArmourPanel.rrd"]}) as server:
        client = server.client()
        dat = client.get_dataset("recording")
        
        #get everything we actually need
        panelDf = dat.filter_contents(["/panels/panel_0/position"]).reader(index="log_time").to_pandas()
        cameraDf = dat.filter_contents(["/camera/**"]).reader(index="log_time").to_pandas()
        panelPos = panelDf["/panels/panel_0/position:Points3D:positions"].to_numpy()
        panels = [p[0].tolist() for p in panelPos]
        frames = cameraDf["/camera/rgb:Image:buffer"].to_numpy()
        times = panelDf.index.to_numpy()
        

    if(server.is_running()):
        server.shutdown()
    return (panels, frames, times)

if __name__ == "__main__":
    panel, frame, times = readDat()
    Simulation(panel, frame, times)