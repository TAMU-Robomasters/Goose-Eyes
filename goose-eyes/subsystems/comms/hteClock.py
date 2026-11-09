import os
import select
import struct
import time


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
        self._last_reset_timestamp = None

        self.FMT = "<QQII"
        self.event_size = struct.calcsize(self.FMT)

    def update(self, timeout=None):
        """Read available HTE events, optionally without waiting for one."""
        poll_timeout = -1 if timeout is None else timeout
        if not self.poller.poll(poll_timeout):
            return self

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
        Check for a significant gap and update the start pulse if one is found.

        This method performs one non-blocking HTE poll. Call it repeatedly while
        performing other work, such as retransmitting the reset request.
        """
        if self.start_pulse is not None:
            return self.start_pulse, self.start_time

        previous_timestamp = self._last_reset_timestamp
        self.update(timeout=0)

        if self.current_timestamp is None:
            return self.start_pulse, self.start_time

        if previous_timestamp is not None and self.current_pulse is not None:
            delta = self.current_timestamp - previous_timestamp
            if delta > 0.25e9:
                self.start_pulse = self.current_pulse + 1
                self.start_time = self.current_timestamp

        self._last_reset_timestamp = self.current_timestamp
        return self.start_pulse, self.start_time

    def close(self):
        if self.dev is not None:
            self.poller.unregister(self.dev)
            os.close(self.dev)
            self.dev = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
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
