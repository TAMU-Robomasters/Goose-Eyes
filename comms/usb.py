import serial
import hteClock


class usb_comms:
    def __init__(self, port, buad, packet_size):
        self.ser = serial.Serial(port, buad, timeout=1)
        self.packet_size = packet_size
        self.hte = hteClock.HTEClockEvent("/dev/hte_clock0")

    def send(self, data):
        data = data.ljust(self.packet_size, b"\x00")
        self.ser.write(data)

    def receive(self):
        return self.ser.read(self.packet_size)

    def reset_start_pulse(self):
        """
        Reset the start pulse of the HTE clock.

        Sends a reset command to the USB device and waits for the HTE clock
        to register the start pulse. Returns the start pulse and start time.
        """
        self.send(b"r")
        self.hte.reset_start_pulse()
        return self.hte.start_pulse, self.hte.start_time


if __name__ == "__main__":
    usb = usb_comms("/dev/ttyACM0", 921600, 64)
    print("starting ...")
    start_pulse, start_time = usb.reset_start_pulse()
    print("Start pulse:", start_pulse, "Start time:", start_time)
    for i in range(10):
        recv = usb.receive()
        print("Received:", recv)
        usb.hte.update()
        print(
            usb.hte.current_timestamp - usb.hte.start_time,
            usb.hte.current_pulse - usb.hte.start_pulse,
            usb.hte.gpio,
            usb.hte.edge,
        )
