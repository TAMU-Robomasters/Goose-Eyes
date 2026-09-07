import os
import select
import struct


class HTEClockEvent:
    def __init__(self, dev):
        self.dev = os.open(dev, os.O_RDONLY)
        self.poller = select.poll()
        self.poller.register(self.dev, select.POLLIN)
        self.current_timestamp = None  # jetson ns clock
        self.current_pulse = None
        self.gpio = None
        self.edge = None
        self.start_pulse = None
        self.start_time = None

        self.FMT = "<QQII"
        self.event_size = struct.calcsize(self.FMT)

    def update(self):
        self.poller.poll()

        latest = None

        while True:
            data = os.read(self.dev, self.event_size)

            if len(data) != self.event_size:
                break

            latest = struct.unpack(self.FMT, data)

            if not self.poller.poll(0):
                break

        if latest:
            (
                self.current_timestamp,
                self.current_pulse,
                self.gpio,
                self.edge,
            ) = latest

        return self

    def reset_start_pulse(self):
        """
        Reset the start pulse of the HTE clock.

        Waits for a significant time delta between consecutive events to determine the start pulse.
        Sets the start pulse and start time once detected.
        """
        last_timestamp = None
        while self.start_pulse is None:
            self.update()
            if last_timestamp is not None:
                delta = self.current_timestamp - last_timestamp
                print("Delta:", delta)
                if delta > 0.25e9:
                    self.start_pulse = self.current_pulse + 1
                    self.start_time = self.current_timestamp

            last_timestamp = self.current_timestamp

    def close(self):
        if self.dev is not None:
            self.poller.unregister(self.dev)
            os.close(self.dev)
            self.dev = None

    def __enter__(self):
        return self

    def __exit__(self):
        self.close()


if __name__ == "__main__":
    import time

    with HTEClockEvent("/dev/hte_clock0") as clock_event:
        print("Resetting start pulse...")
        clock_event.reset_start_pulse()
        print(
            "Start pulse:",
            clock_event.start_pulse,
            "Start time:",
            clock_event.start_time,
        )
        while True:
            clock_event.update()
            print(
                clock_event.current_timestamp,
                clock_event.current_pulse,
                clock_event.gpio,
                clock_event.edge,
            )
            time.sleep(1)
