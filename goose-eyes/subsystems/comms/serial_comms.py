import time
from typing import Optional

import commStructs
import hteClock
import serial

MAGIC = b"\x69\x42"


def checksum8(data: bytes) -> int:
    return sum(data) & 0xFF


class serial_comms:
    def __init__(
        self,
        port,
        baudrate=115200,
        packet_size=64,
        timeout=1000,
    ):
        self.packet_size = packet_size
        self.timeout = timeout
        self.rx_buffer = b""

        self.dev = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout / 1000.0,
        )

        self.hte = hteClock.HTEClockEvent("/dev/hte_clock0")

    def send_raw(self, data: bytes):
        if not isinstance(data, bytes):
            raise TypeError("send_raw expects bytes")

        total_sent = 0

        while total_sent < len(data):
            sent = self.dev.write(data[total_sent:])

            if sent is None or sent <= 0:
                raise OSError("Serial write made no progress")

            total_sent += sent

    def send_packet(self, packet):
        payload = packet.pack()
        framed_packet = MAGIC + payload + bytes([checksum8(payload)])
        self.send_raw(framed_packet)

    def send_query(self, timestamp: int, request_number: int):
        packet = commStructs.QueryPacket(
            timestamp=timestamp, requestNumber=request_number
        )

        self.send_packet(packet)

    def receive_chunk(self, timeout=None):
        if timeout is None:
            timeout = self.timeout

        previous_timeout = self.dev.timeout
        self.dev.timeout = timeout / 1000.0

        try:
            return self.dev.read(self.packet_size)
        finally:
            self.dev.timeout = previous_timeout

    def read_exact(self, num_bytes: int, timeout=None) -> Optional[bytes]:
        if timeout is None:
            timeout = self.timeout

        deadline = time.monotonic() + timeout / 1000.0

        while len(self.rx_buffer) < num_bytes:
            remaining_time = deadline - time.monotonic()

            if remaining_time <= 0:
                partial_len = len(self.rx_buffer)
                self.rx_buffer = b""
                print(
                    f"Timed out waiting for {num_bytes} bytes. "
                    f"Only received {partial_len} bytes."
                )
                return None

            chunk_timeout_ms = max(1, int(remaining_time * 1000))
            chunk = self.receive_chunk(timeout=chunk_timeout_ms)

            if chunk:
                self.rx_buffer += chunk

        data = self.rx_buffer[:num_bytes]
        self.rx_buffer = self.rx_buffer[num_bytes:]

        return data

    def wait_for_magic(self, timeout=None):
        if timeout is None:
            timeout = self.timeout

        deadline = time.monotonic() + timeout / 1000.0

        while True:
            idx = self.rx_buffer.find(MAGIC)

            if idx >= 0:
                self.rx_buffer = self.rx_buffer[idx + len(MAGIC) :]
                return True

            if len(self.rx_buffer) > len(MAGIC) - 1:
                self.rx_buffer = self.rx_buffer[-(len(MAGIC) - 1) :]

            remaining_time = deadline - time.monotonic()

            if remaining_time <= 0:
                print("Timed out waiting for packet magic")
                return False

            chunk_timeout_ms = max(1, int(remaining_time * 1000))
            chunk = self.receive_chunk(timeout=chunk_timeout_ms)

            if chunk:
                self.rx_buffer += chunk

    def read_packet(self, packet_class, timeout=None):
        if timeout is None:
            timeout = self.timeout

        deadline = time.monotonic() + timeout / 1000.0

        while True:
            remaining_time = deadline - time.monotonic()

            if remaining_time <= 0:
                raise TimeoutError("Timed out waiting for valid framed packet")

            if not self.wait_for_magic(timeout=int(remaining_time * 1000)):
                return None

            remaining_time = deadline - time.monotonic()

            if remaining_time <= 0:
                print("Timed out after packet magic")
                return None

            payload = self.read_exact(
                packet_class.SIZE, timeout=int(remaining_time * 1000)
            )

            if payload is None:
                return None

            remaining_time = deadline - time.monotonic()

            if remaining_time <= 0:
                print("Timed out waiting for checksum")
                return None

            received_checksum = self.read_exact(1, timeout=int(remaining_time * 1000))
            if not received_checksum:
                print("Timed out waiting for checksum")
                return None

            received_checksum = received_checksum[0]
            calculated_checksum = checksum8(payload)

            if received_checksum == calculated_checksum:
                return packet_class.unpack(payload)

            print(
                "Bad checksum. Expected",
                calculated_checksum,
                "got",
                received_checksum,
                "- resyncing...",
            )

    def drain_rx(self):
        self.rx_buffer = b""

        while True:
            chunk = self.receive_chunk(timeout=10)

            if not chunk:
                break

    def query_gimbal(self, timestamp=0, timeout=None, flush_stale=False):
        if flush_stale:
            self.drain_rx()

        self.send_query(
            timestamp=timestamp, request_number=commStructs.REQUEST_GIMBAL_POS
        )

        return self.read_packet(commStructs.GimbalPacket, timeout=timeout)

    def reset_start_pulse(self):
        self.hte.start_pulse = None
        self.hte.start_time = None

        while self.hte.start_pulse is None:
            self.send_query(timestamp=0, request_number=commStructs.REQUEST_RESET)
            self.hte.reset_start_pulse()

        return self.hte.start_pulse, self.hte.start_time

    def close(self):
        if self.dev.is_open:
            self.dev.close()

        self.hte.close()


if __name__ == "__main__":
    PORT = "/dev/ttyTHS1"
    BAUDRATE = 460800

    serial_dev = serial_comms(PORT, baudrate=BAUDRATE, packet_size=64, timeout=1000)

    print("starting ...")

    try:
        serial_dev.drain_rx()
        time.sleep(0.5)

        start_pulse, start_time = serial_dev.reset_start_pulse()

        time.sleep(1)

        print("Start pulse:", start_pulse)
        print("Start time:", start_time)

        serial_dev.drain_rx()

        while True:
            serial_dev.hte.update()

            if serial_dev.hte.current_pulse is None:
                continue

            timestamp = serial_dev.hte.current_pulse - serial_dev.hte.start_pulse

            print("Jetson pulse", timestamp)

            gimbal = serial_dev.query_gimbal(timestamp=timestamp, timeout=1000)

            if gimbal is None:
                print("Failed to receive gimbal data")
                continue

            print(
                "Received gimbal:",
                "timestamp =",
                gimbal.timestamp,
                "yaw =",
                gimbal.yaw,
                "pitch =",
                gimbal.pitch,
            )
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nCtrl+C received.")
        serial_dev.send_query(timestamp=0, request_number=commStructs.REQUEST_RESET)
        time.sleep(0.05)

    finally:
        serial_dev.close()
        print("done")
