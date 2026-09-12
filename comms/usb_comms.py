import usb.core
import usb.util
import hteClock


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

    def build_message(self, **fields):
        """
        Build a message like:

            :timestamp=12345678:num1=100:num2=200:\\n
        """
        parts = []

        for name, value in fields.items():
            name = str(name)
            value = str(value)

            if ":" in name or "=" in name or "\n" in name:
                raise ValueError(f"Invalid field name: {name}")

            if ":" in value or "\n" in value:
                raise ValueError(f"Invalid field value: {value}")

            parts.append(f"{name}={value}")

        message = ":" + ":".join(parts) + ":\n"
        return message.encode("ascii")

    def send_raw(self, data):
        """
        Send raw bytes or string.

        No padding is used.
        """
        if isinstance(data, str):
            data = data.encode("ascii")

        self.ep_out.write(data, timeout=self.timeout)

    def send_message(self, **fields):
        """
        Send a formatted protocol message.

        Example:

            self.send_message(timestamp=12345678, num1=100, num2=200)

        Sends:

            :timestamp=12345678:num1=100:num2=200:\\n
        """
        data = self.build_message(**fields)
        self.send_raw(data)

    def receive_chunk(self):
        """
        Read one USB chunk.

        This may be a full message, part of a message, or multiple messages.
        """
        try:
            data = self.ep_in.read(self.packet_size, timeout=self.timeout)
            return bytes(data)

        except usb.core.USBError as e:
            # Timeout is normal if no data arrived.
            if e.errno == 110:
                return b""

            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                return b""

            raise

    def receive_messages(self, max_reads=100):
        """
        Read many USB chunks and parse all complete messages.

        max_reads limits how much time we spend draining USB in one call.
        """
        messages = []

        for _ in range(max_reads):
            chunk = self.receive_chunk()

            if not chunk:
                break

            self.rx_buffer += chunk

            while b"\n" in self.rx_buffer:
                line, self.rx_buffer = self.rx_buffer.split(b"\n", 1)
                line = line.strip()

                if not line:
                    continue

                try:
                    msg = self.parse_message(line)
                    messages.append(msg)
                except ValueError as e:
                    print("Bad message:", e, "line:", line)

        return messages

    def parse_message(self, line):
        """
        Parse one complete message without the newline.

        Input:

            b":timestamp=12345678:num1=100:num2=200:"

        Output:

            {
                "timestamp": 12345678,
                "num1": 100,
                "num2": 200
            }
        """
        text = line.decode("ascii")

        if not text.startswith(":"):
            raise ValueError(f"Bad message start: {text}")

        if not text.endswith(":"):
            raise ValueError(f"Bad message end: {text}")

        # Remove first and last colon.
        text = text[1:-1]

        result = {}

        if text == "":
            return result

        fields = text.split(":")

        for field in fields:
            if "=" not in field:
                raise ValueError(f"Bad field: {field}")

            name, value = field.split("=", 1)

            # Convert numeric values to int when possible.
            try:
                value = int(value)
            except ValueError:
                pass

            result[name] = value

        return result

    def reset_start_pulse(self):
        """
        Send reset command and reset HTE start pulse.

        Sends:

            :cmd=r:\\n
        """
        self.send_message(cmd="r")
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

    usb_dev = usb_comms(VID, PID, packet_size=1344)

    print("starting ...")

    start_pulse, start_time = usb_dev.reset_start_pulse()

    print("Start pulse:", start_pulse, "Start time:", start_time)

    # Example send using your format.
    usb_dev.send_message(
        timestamp=0,
        num1=0,
        num2=0
    )
    try:
        while True:
            messages = usb_dev.receive_messages()

            for msg in messages:
                print("Received:", msg)

                usb_dev.hte.update()

                print("Jetson pulse" ,usb_dev.hte.current_pulse - usb_dev.hte.start_pulse)

    except KeyboardInterrupt:
        pass
    finally:
        usb_dev.close()