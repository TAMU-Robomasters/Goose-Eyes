import time

import commStructs
import hteClock
import usb.core
import usb.util

MAGIC = b"\x69\x42"


def checksum8(data: bytes) -> int:
    return sum(data) & 0xFF


class usb_comms:
    def __init__(self, vid, pid, packet_size=64, interface=None, timeout=1000):
        self.packet_size = packet_size
        self.timeout = timeout
        self.rx_buffer = b""

        self.dev = usb.core.find(idVendor=vid, idProduct=pid)

        if self.dev is None:
            raise RuntimeError(
                f"USB device not found: VID=0x{vid:04x}, PID=0x{pid:04x}"
            )

        if interface is None:
            interface = self.find_bulk_interface()

        self.interface = interface

        if self.dev.is_kernel_driver_active(self.interface):
            self.dev.detach_kernel_driver(self.interface)

        self.dev.set_configuration()

        cfg = self.dev.get_active_configuration()

        intf = usb.util.find_descriptor(cfg, bInterfaceNumber=self.interface)

        if intf is None:
            raise RuntimeError(f"Interface {self.interface} not found")

        usb.util.claim_interface(self.dev, self.interface)

        self.ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
                and usb.util.endpoint_type(e.bmAttributes)
                == usb.util.ENDPOINT_TYPE_BULK
            ),
        )

        self.ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
                and usb.util.endpoint_type(e.bmAttributes)
                == usb.util.ENDPOINT_TYPE_BULK
            ),
        )

        if self.ep_out is None:
            raise RuntimeError("Bulk OUT endpoint not found")

        if self.ep_in is None:
            raise RuntimeError("Bulk IN endpoint not found")

        self.hte = hteClock.HTEClockEvent("/dev/hte_clock0")

    def find_bulk_interface(self):
        cfg = self.dev[0]

        for intf in cfg:
            has_in = False
            has_out = False

            for ep in intf:
                ep_type = usb.util.endpoint_type(ep.bmAttributes)
                ep_dir = usb.util.endpoint_direction(ep.bEndpointAddress)

                if ep_type == usb.util.ENDPOINT_TYPE_BULK:
                    if ep_dir == usb.util.ENDPOINT_IN:
                        has_in = True
                    elif ep_dir == usb.util.ENDPOINT_OUT:
                        has_out = True

            if has_in and has_out:
                return intf.bInterfaceNumber

        raise RuntimeError("No bulk IN/OUT interface found")

    def send_raw(self, data: bytes):
        if not isinstance(data, bytes):
            raise TypeError("send_raw expects bytes")

        total_sent = 0

        while total_sent < len(data):
            sent = self.ep_out.write(data[total_sent:], timeout=self.timeout)

            if sent is None:
                sent = len(data) - total_sent

            if sent <= 0:
                raise OSError("USB write made no progress")

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

        try:
            data = self.ep_in.read(self.packet_size, timeout=timeout)
            return bytes(data)

        except usb.core.USBError as e:
            if getattr(e, "errno", None) == 110:
                return b""

            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                return b""

            raise

    def read_exact(self, num_bytes: int, timeout=None) -> bytes:
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
                return

            if len(self.rx_buffer) > len(MAGIC) - 1:
                self.rx_buffer = self.rx_buffer[-(len(MAGIC) - 1) :]

            remaining_time = deadline - time.monotonic()

            if remaining_time <= 0:
                print("Timed out waiting for packet magic")
                return

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

            self.wait_for_magic(timeout=int(remaining_time * 1000))

            remaining_time = deadline - time.monotonic()

            if remaining_time <= 0:
                print("Timed out after packet magic")
                return None

            payload = self.read_exact(
                packet_class.SIZE, timeout=int(remaining_time * 1000)
            )

            remaining_time = deadline - time.monotonic()

            if remaining_time <= 0:
                print("Timed out waiting for checksum")
                return None
                # raise TimeoutError("Timed out waiting for checksum")

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
        usb.util.release_interface(self.dev, self.interface)

        usb.util.dispose_resources(self.dev)


if __name__ == "__main__":
    VID = 0x0483
    PID = 0x5740

    usb_dev = usb_comms(VID, PID, packet_size=64, timeout=1000)

    print("starting ...")

    try:
        usb_dev.drain_rx()
        time.sleep(0.5)

        start_pulse, start_time = usb_dev.reset_start_pulse()

        time.sleep(1)

        print("Start pulse:", start_pulse)
        print("Start time:", start_time)

        usb_dev.drain_rx()

        while True:
            usb_dev.hte.update()

            timestamp = usb_dev.hte.current_pulse - usb_dev.hte.start_pulse

            print("Jetson pulse", timestamp)

            gimbal = usb_dev.query_gimbal(timestamp=timestamp, timeout=1000)

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
            time.sleep(0.05)  # Small delay to prevent overwhelming the USB interface

    except KeyboardInterrupt:
        print("\nCtrl+C received.")

        usb_dev.send_query(timestamp=0, request_number=commStructs.REQUEST_RESET)
        time.sleep(0.05)

    finally:
        usb_dev.close()
        print("done")
