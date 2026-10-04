import time

import commStructs
from usb_comms import usb_comms

from dataclasses import dataclass

class gimbalSub:
    def __init__(self, pid=0x5740, vid=0x0483):
        self.pid = pid
        self.vid = vid
        self.comm_obj = usb_comms(vid, pid)
        self.gimbal = None


        ## BEGINNING FUNCTIONS
        self.comm_obj.drain_rx()
        time.sleep(0.5)

        start_pulse, start_time = self.comm_obj.reset_start_pulse()
        time.sleep(1)
        self.comm_obj.drain_rx()

    def setGimbal(self):
        try:
            self.comm_obj.hte.update()
            self.timestamp = self.comm_obj.hte.current_pulse - self.comm_obj.hte.start_pulse
            self.gimbal = self.comm_obj.query_gimbal(self.timestamp)
            if self.gimbal is None:
                print("Failed to receive gimbal data")
                return False
            print(f"Timestamp: {self.gimbal.timestamp}\n Yaw: {self.gimbal.yaw}\n Pitch: {self.gimbal.pitch}")
            time.sleep(0.05)
            return True


        except TimeoutError:
            print("\nTimeout Error! Be quicker next time!")
            time.sleep(0.05)
            return False



    def getGimbal(self):
        return self.gimbal

    def closeGimbal(self):
        self.comm_obj.send_query(timestamp=0, request_number=commStructs.REQUEST_RESET)
        self.comm_obj.close()