"""
UART communication to send messages to embedded system and receive transformation matrix data for auto aim.
"""

from ctypes import Structure, c_ubyte, c_uint8, c_float, sizeof, Array, c_bool
from enum import Enum
from typing import List

from numpy.testing import print_assert_equal
import hteClock
import serial
import time
import numpy as np
import numpy.typing as npt

SERIAL_PORT: str = "/dev/ttyTHS1"
BAUDRATE: int = 460800
DEBUG = True

class CVState(Enum):
    PANEL_NOT_IN_VIEW: int = 0
    PANEL_IN_VIEW: int = 1
    FIRE: int = 2


# Struct definitions matching C++ packed structs
class JetsonMessage(Structure):
    """Message struct to send to embedded system (JetsonMessage)"""
    _pack_ = 1
    _fields_ = [
        ("magic", c_uint8),
        ("messageType", c_uint8),
        ("pitch", c_float),  # pitch angle in radians
        ("yaw", c_float),  # yaw angle in radians
        ("timeUntilNextFire", c_uint8), # in ms. Max value is 255 ms
        ("cvState", c_uint8),  # CVState (assuming uint8_t) // 1 if a panel is detected
    ]
    magic: int
    messageType: int
    pitch: float
    yaw: float
    timeUntilNextFire: int
    cvState: CVState


class QueryToEmbedded(Structure):
    """Query struct to send to embedded system with magic, messageType, and frame delay"""
    _pack_ = 1
    _fields_ = [
        ("magic", c_uint8),
        ("messageType", c_uint8),
        ("frameDelay_ms", c_uint8),  # frame delay in milliseconds
    ]
    magic: int
    messageType: int
    frameDelay_ms: int

class QueryToEmbeddedReset(Structure):
    """Query struct to send to embedded system with magic, messageType, and frame delay"""
    _pack_ = 1
    _fields_ = [
        ("magic", c_uint8),
        ("messageType", c_uint8),
        ("some_bs", c_bool),  # frame delay in milliseconds
    ]
    magic: int
    messageType: int
    frameDelay_ms: int


HTE_RESET_MESSAGE_TYPE = 3


class EmbeddedTransformationMessage(Structure):
    """Response struct from embedded system with transformation matrix"""
    _pack_ = 1
    _fields_ = [
        ("magic", c_uint8),
        ("yaw", c_float),  # yaw angle in radians
        ("pitch", c_float),  # pitch angle in radians
        ("matrix", c_float * 16),  # 4x4 transformation matrix (row-major order)
    ]
    magic: int
    yaw: float
    pitch: float
    matrix: List[float]


class EmbeddedCommunicator():
    def __init__(self):
        self.port = self._setup_serial_port()
        if self.port is None:
            if DEBUG:
                print("[UART]: Failed to setup serial port. Exiting.")
            return

        self.hte = hteClock.HTEClockEvent("/dev/hte_clock0")

        # Clear any existing data in buffer
        self.port.reset_input_buffer()
        self.port.reset_output_buffer()

    def get_camera_to_ballistic_transformation(self, milliseconds_in_the_past: int) -> npt.NDArray[np.float64] | None:
        if self._send_query_to_embedded(milliseconds_in_the_past):
            if (message := self._read_transformation_message()) is not None:
                return message.yaw, message.pitch, np.array([*message.matrix], dtype=np.float64).reshape((4,4))

        return None # Something failed

    def send_angles_to_embedded(self, pitch: float, yaw: float, timeUntilNextFire: int, \
                                 cvState: CVState, magic: str = 'a', messageType: str = 'd') -> bool:
        """Send JetsonMessage to embedded system"""
        message = JetsonMessage(
            magic=ord(magic),
            messageType=ord(messageType),
            pitch=float(pitch),
            yaw=float(yaw),
            timeUntilNextFire=c_uint8(timeUntilNextFire),
            cvState=c_uint8(cvState).value
        )
        if DEBUG:
            print(f'[UART]: Sending message to embedded:')
            print(f'  magic={chr(message.magic)}, messageType={chr(message.messageType)}')
            print(f'  pitch={message.pitch:.4f} radians ({message.pitch * 180 / np.pi:.2f} degrees)')
            print(f'  yaw={message.yaw:.4f} radians ({message.yaw * 180 / np.pi:.2f} degrees)')
            print(f'  timeUntilNextFire={message.timeUntilNextFire} ms')
            print(f'  cvState={message.cvState}')

        try:
            self.port.write(bytes(message))
            if DEBUG:
                print(f'[UART]: Message sent successfully ({len(bytes(message))} bytes)')
            return True
        except Exception as error:
            if DEBUG:
                print(f'[UART]: Error sending message: {error}')
            return False

    def _setup_serial_port(self) -> serial.Serial | None:
        """Setup and return serial port connection"""
        if DEBUG:
            print(f'[UART]: Setting up port={SERIAL_PORT}, baudrate={BAUDRATE}')
        try:
            return serial.Serial(
                SERIAL_PORT,
                baudrate=BAUDRATE,
                timeout=1.0,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
        except Exception as error:
            if DEBUG:
                print(f'[UART]: Error setting up serial port: {error}')
            import subprocess
            # Attempt to fix permissions (similar to existing code)
            try:
                subprocess.run(["bash", "-c", f"sudo -S chmod 777 '{SERIAL_PORT}' <<<  \"$(cat \"$HOME/.pass\")\" "],
                             check=False)
                return self._setup_serial_port()  # retry
            except:
                raise

    def _send_query_to_embedded(self, frameDelay_ms: int, magic: str = 'a', \
                               messageType: str = 't') -> bool:
        """Send query to embedded with magic, messageType, and frame delay"""
        query = QueryToEmbedded(
            magic=ord(magic),
            messageType=ord(messageType),
            frameDelay_ms=c_uint8(frameDelay_ms).value
        )

        if DEBUG:
            print(f'[UART]: Sending query to embedded:')
            print(f'  magic={chr(query.magic)}, messageType={chr(query.messageType)}')
            print(f'  frameDelay_ms={query.frameDelay_ms}ms')

        try:
            self.port.write(bytes(query))
            if DEBUG:
                print(f'[UART]: Query sent successfully ({len(bytes(query))} bytes)')
            return True
        except Exception as error:
            if DEBUG:
                print(f'[UART]: Error sending query: {error}')
            return False


    def reset_start_pulse(self) -> tuple[int | None, int | None]:
        """Reset the HTE start pulse and wait for the next significant gap."""
        self.hte.start_pulse = None
        self.hte.start_time = None
        self.hte.reset_start_pulse()
        return self.hte.start_pulse, self.hte.start_time

    def update_hte(self) -> int | None:
        """Read the latest HTE event and return its pulse relative to startup."""
        self.hte.update()

        if self.hte.current_pulse is None or self.hte.start_pulse is None:
            return None

        return self.hte.current_pulse - self.hte.start_pulse

    def reset_hte_clock(self) -> tuple[int | None, int | None]:
        """Request an HTE reset from the embedded system and re-arm the HTE clock."""
        port = self.port
        if port is None:
            raise RuntimeError("Cannot reset HTE clock without an open serial port")

        self.hte.start_pulse = None
        self.hte.start_time = None

        while self.hte.start_pulse is None:
            reset_message = QueryToEmbeddedReset(
                magic=ord('a'),
                messageType=HTE_RESET_MESSAGE_TYPE,
                some_bs=1,
            )
            port.write(bytes(reset_message))
            self.hte.reset_start_pulse()

        return self.hte.start_pulse, self.hte.start_time

    def _read_transformation_message(self) -> EmbeddedTransformationMessage | None:
        """Wait for and read EmbeddedTransformationMessage from UART"""
        expected_size = sizeof(EmbeddedTransformationMessage())
        if DEBUG:
            print(f'[UART]: Waiting for transformation message ({expected_size} bytes)...')

        # Wait until we have enough bytes
        start_time = time.time()
        timeout = 5.0  # 5 second timeout

        while self.port.in_waiting < expected_size:
            if time.time() - start_time > timeout:
                if DEBUG:
                    print(f'[UART]: Timeout waiting for message (have {self.port.in_waiting} bytes, need {expected_size})')
                return None
            time.sleep(0.01)  # Small delay to avoid busy waiting
            if DEBUG:
                print(f'[UART]: Currently {self.port.in_waiting} bytes in port')

        # Read the exact number of bytes needed
        data = self.port.read(expected_size)

        if len(data) != expected_size:
            if DEBUG:
                print(f'[UART]: Read {len(data)} bytes, expected {expected_size}')
            return None

        # Cast to struct
        transformation = EmbeddedTransformationMessage.from_buffer_copy(data)

        return transformation

    def close(self) -> None:
        """Close the UART and HTE resources."""
        port = getattr(self, "port", None)
        if port is not None and port.is_open:
            port.close()

        hte = getattr(self, "hte", None)
        if hte is not None:
            hte.close()


if __name__ == "__main__":
    communicator = EmbeddedCommunicator()

    try:
        print("Sending HTE reset message (message type 3)...")
        start_pulse, start_time = communicator.reset_hte_clock()
        print("HTE start pulse:", start_pulse)
        print("HTE start time:", start_time)

        while True:
            relative_pulse = communicator.update_hte()
            print(
                "Current HTE pulse:",
                communicator.hte.current_pulse,
                "Relative pulse:",
                relative_pulse,
            )
    except KeyboardInterrupt:
        print("\nCtrl+C received.")
    finally:
        communicator.close()
