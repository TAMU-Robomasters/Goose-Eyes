import time
import usb.core
import usb.util

import hteClock
import commStructs


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

        # Pick an interface with bulk IN and bulk OUT endpoints.
        if interface is None:
            interface = self.find_bulk_interface()

        self.interface = interface

        # Detach kernel driver if Linux claimed this interface.
        try:
            if self.dev.is_kernel_driver_active(self.interface):
                self.dev.detach_kernel_driver(self.interface)
        except Exception:
            pass

        self.dev.set_configuration()

        cfg = self.dev.get_active_configuration()

        intf = usb.util.find_descriptor(
            cfg,
            bInterfaceNumber=self.interface
        )

        if intf is None:
            raise RuntimeError(f"Interface {self.interface} not found")

        usb.util.claim_interface(self.dev, self.interface)

        self.ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e:
                usb.util.endpoint_direction(e.bEndpointAddress)
                == usb.util.ENDPOINT_OUT
                and usb.util.endpoint_type(e.bmAttributes)
                == usb.util.ENDPOINT_TYPE_BULK
        )

        self.ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e:
                usb.util.endpoint_direction(e.bEndpointAddress)
                == usb.util.ENDPOINT_IN
                and usb.util.endpoint_type(e.bmAttributes)
                == usb.util.ENDPOINT_TYPE_BULK
        )

        if self.ep_out is None:
            raise RuntimeError("Bulk OUT endpoint not found")

        if self.ep_in is None:
            raise RuntimeError("Bulk IN endpoint not found")

        self.hte = hteClock.HTEClockEvent("/dev/hte_clock0")

    def find_bulk_interface(self):
        """
        Find the first USB interface with one bulk IN and one bulk OUT endpoint.
        """
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
        """
        Send raw bytes over bulk OUT.
        """
        if not isinstance(data, bytes):
            raise TypeError("send_raw expects bytes")

        self.ep_out.write(data, timeout=self.timeout)

    def send_packet(self, packet):
        """
        Send a packet object that has a pack() method.
        """
        self.send_raw(packet.pack())

    def send_query(self, timestamp: int, request_number: int):
        """
        Send a QueryPacket to the dev board.

        The dev board should decode this and only respond if the request
        requires a response.
        """
        packet = commStructs.QueryPacket(
            timestamp=timestamp,
            requestNumber=request_number
        )

        self.send_packet(packet)

    def receive_chunk(self, timeout=None):
        """
        Read one USB chunk from bulk IN.

        This may return:
            - empty bytes on timeout
            - part of a packet
            - one full packet
            - multiple packets
        """
        if timeout is None:
            timeout = self.timeout

        try:
            data = self.ep_in.read(self.packet_size, timeout=timeout)
            return bytes(data)

        except usb.core.USBError as e:
            # Timeout is normal if no data arrived.
            if getattr(e, "errno", None) == 110:
                return b""

            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                return b""

            raise

    def read_exact(self, num_bytes: int, timeout=None) -> bytes:
        """
        Read exactly num_bytes from USB.

        This function uses self.rx_buffer so it handles cases where USB gives:
            - less than one packet
            - exactly one packet
            - more than one packet

        Raises TimeoutError if not enough bytes arrive before timeout.
        """
        if timeout is None:
            timeout = self.timeout

        deadline = time.monotonic() + timeout / 1000.0

        while len(self.rx_buffer) < num_bytes:
            remaining_time = deadline - time.monotonic()

            if remaining_time <= 0:
                raise TimeoutError(
                    f"Timed out waiting for {num_bytes} bytes. "
                    f"Only received {len(self.rx_buffer)} bytes."
                )

            chunk_timeout_ms = max(1, int(remaining_time * 1000))

            chunk = self.receive_chunk(timeout=chunk_timeout_ms)

            if chunk:
                self.rx_buffer += chunk

        data = self.rx_buffer[:num_bytes]
        self.rx_buffer = self.rx_buffer[num_bytes:]

        return data

    def read_packet(self, packet_class, timeout=None):
        """
        Read one fixed-size packet and unpack it.

        packet_class must have:
            SIZE
            unpack(data)
        """
        data = self.read_exact(packet_class.SIZE, timeout=timeout)
        return packet_class.unpack(data)

    def drain_rx(self):
        """
        Clear any pending/stale USB input data.

        Useful during startup or error recovery.
        """
        self.rx_buffer = b""

        while True:
            chunk = self.receive_chunk(timeout=10)

            if not chunk:
                break

    def query_gimbal(self, timestamp=0, timeout=None, flush_stale=False):
        """
        Query/receive transaction for gimbal position.

        Flow:

            Jetson -> dev board:
                QueryPacket(timestamp, REQUEST_GIMBAL_POS)

            dev board -> Jetson:
                GimbalPacket(timestamp, yaw, pitch)
        """
        if flush_stale:
            self.drain_rx()

        self.send_query(
            timestamp=timestamp,
            request_number=commStructs.REQUEST_GIMBAL_POS
        )

        return self.read_packet(
            commStructs.GimbalPacket,
            timeout=timeout
        )

    def reset_start_pulse(self):
        """
        Send reset request and reset HTE start pulse.

        This assumes REQUEST_RESET is a command that does not return data.

        If your firmware sends back an acknowledgment packet for reset,
        then you should add a read_packet() call here for that ack packet.
        """
        self.send_query(
            timestamp=0,
            request_number=commStructs.REQUEST_RESET
        )

        self.hte.reset_start_pulse()

        return self.hte.start_pulse, self.hte.start_time

    def close(self):
        try:
            usb.util.release_interface(self.dev, self.interface)
        except Exception:
            pass

        usb.util.dispose_resources(self.dev)


if __name__ == "__main__":
    # Replace these with your actual VID/PID from lsusb.
    VID = 0x0483
    PID = 0x5740

    usb_dev = usb_comms(
        VID,
        PID,
        packet_size=64,
        timeout=1000
    )

    print("starting ...")

    try:
        usb_dev.drain_rx()

        start_pulse, start_time = usb_dev.reset_start_pulse()

        print("Start pulse:", start_pulse)
        print("Start time:", start_time)
        # Optional: clear anything stale after reset.

        while True:
            try:
                usb_dev.hte.update()
                print("Jetson pulse",usb_dev.hte.current_pulse - usb_dev.hte.start_pulse
                )
                gimbal = usb_dev.query_gimbal(
                    timestamp=usb_dev.hte.current_pulse - usb_dev.hte.start_pulse,
                    timeout=1000
                )

                print(
                    "Received gimbal:",
                    "timestamp =", gimbal.timestamp,
                    "yaw =", gimbal.yaw,
                    "pitch =", gimbal.pitch
                )
                time.sleep(1)
            except Exception as e:
                print("Error during communication:", e)


    except KeyboardInterrupt:
        pass

    finally:
        usb_dev.close()