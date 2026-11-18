"""USB CDC communication with the embedded development board."""

from ctypes import Structure, c_uint8, c_uint16, c_uint32, c_float, sizeof
from enum import Enum
from typing import List

import serial
import time
import numpy as np
import numpy.typing as npt

import hteClock

SERIAL_PORT: str = "/dev/ttyACM0"
BAUDRATE: int = 460800
DEBUG = False

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
        ("timeUntilNextFire", c_uint16), # in ms
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
        ("pulse", c_uint32),  # clock pulse
    ]
    magic: int
    messageType: int
    pulse: int

class QueryToEmbeddedReset(Structure):
    """Query struct to send to embedded system with magic, messageType, and frame delay"""
    _pack_ = 1
    _fields_ = [
        ("magic", c_uint8),
        ("messageType", c_uint8),
        ("some_bs", c_uint8),  # frame delay in milliseconds
    ]
    magic: int
    messageType: int
    some_bs: bool


HTE_RESET_MESSAGE_TYPE = 3


class EmbeddedTransformationMessage(Structure):
    """Response struct from embedded system with transformation matrix"""
    _pack_ = 1
    _fields_ = [
        ("magic", c_uint8),
        ("yaw", c_float),  # yaw angle in radians
        ("pitch", c_float),  # pitch angle in radians
        ("roll", c_float),  # roll angle in radians
        ("matrix", c_float * 16),  # 4x4 transformation matrix (row-major order)
    ]
    magic: int
    yaw: float
    pitch: float
    roll: float
    matrix: List[float]

class EmbeddedUniversalPacket(Structure):
    """Universal packet struct from embedded system"""
    _pack_ = 1
    _fields_ = [
        ("magic", c_uint8),
        ("currTicks", c_uint32),
        # odometry information
        ("x_odom", c_float),
        ("y_odom", c_float),
        ("theta_odom", c_float),
        #transformation for aiming
        ("yaw", c_float),
        ("pitch", c_float),
        ("roll", c_float),
        ("matrix", c_float * 16)
    ]
    magic: int
    currTicks: int
    x_odom: float
    y_odom: float
    theta_odom: float
    yaw: float
    pitch: float
    roll: float
    matrix: List[float]


class EmbeddedCommunicator():
    def __init__(self):
        self.port = self._setup_serial_port()
        if self.port is None:
            if DEBUG:
                print("[UART]: Failed to setup serial port. Exiting.")
            return

        # Clear any existing data in buffer
        self.port.reset_input_buffer()
        self.port.reset_output_buffer()

        self.hte = hteClock.HTEClockEvent("/dev/hte_clock0")

    def get_camera_to_ballistic_transformation(self, pulse: int) -> npt.NDArray[np.float64] | None:
        if self._send_query_to_embedded(pulse):
            if (message := self._read_transformation_message()) is not None:
                return message.yaw, message.pitch, message.roll, np.array([*message.matrix], dtype=np.float64).reshape((4,4))

        return None # Something failed

    def get_universal_message(self) -> EmbeddedUniversalPacket | None:
        if self._send_query_to_embedded('*'):
            if (message := self._read_universal_message()) is not None:
                return message

        return None # Something failed

    def send_angles_to_embedded(self, pitch: float, yaw: float, timeUntilNextFire: int, \
                                 cvState: CVState, magic: str = 'a', messageType: str = 'd') -> bool:
        """Send JetsonMessage to embedded system"""
        message = JetsonMessage(
            magic=ord(magic),
            messageType=ord(messageType),
            pitch=float(pitch),
            yaw=float(yaw),
            timeUntilNextFire=c_uint16(timeUntilNextFire).value,
            cvState=c_uint8(cvState.value).value
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
            return None

    def _send_query_to_embedded(self, magic: str = 'a', \
                               messageType: str = 't') -> bool:
        """Send query to embedded with magic, messageType, and frame delay"""
        query = QueryToEmbedded(
            magic=ord(magic),
            messageType=ord(messageType),
        )

        if DEBUG:
            print(f'[UART]: Sending query to embedded:')
            print(f'  magic={chr(query.magic)}, messageType={chr(query.messageType)}')
            print(f'  pulse={query.pulse}')

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
        """Reset the embedded HTE clock and establish the local start pulse."""
        self.hte.start_pulse = None
        self.hte.start_time = None
        self.hte._last_reset_timestamp = None

        reset_frame = bytes(QueryToEmbeddedReset(
            magic=ord('a'),
            messageType=HTE_RESET_MESSAGE_TYPE,
            some_bs=0,
        ))

        while self.hte.start_pulse is None:
            try:
                self.port.write(reset_frame)
            except Exception as error:
                if DEBUG:
                    print(f'[UART]: Error sending HTE reset query: {error}')
                return None, None

            self.hte.reset_start_pulse()
            time.sleep(0.01)

        return self.hte.start_pulse, self.hte.start_time

    def update_hte(self) -> int | None:
        """Poll HTE events and return the pulse relative to the reset point."""
        self.hte.update(timeout=0)

        if self.hte.current_pulse is None or self.hte.start_pulse is None:
            return None

        return self.hte.current_pulse - self.hte.start_pulse

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

    def _read_universal_message(self) -> EmbeddedUniversalPacket | None:
        """Wait for and read EmbeddedUniversalPacket from UART"""
        expected_size = sizeof(EmbeddedUniversalPacket())
        if DEBUG:
            print(f'[UART]: Waiting for universal message ({expected_size} bytes)...')

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
        universal_message = EmbeddedUniversalPacket.from_buffer_copy(data)

        return universal_message

    def close(self) -> None:
        """Close the USB serial resource."""
        hte = getattr(self, "hte", None)
        if hte is not None:
            hte.close()

        port = getattr(self, "port", None)
        if port is not None and port.is_open:
            port.close()

if __name__ == "__main__":
    communicator = EmbeddedCommunicator()

    try:
        start_pulse, start_time = communicator.reset_start_pulse()
        print("Start pulse:", start_pulse)
        print("Start time:", start_time)

        while True:
            timestamp = communicator.update_hte()
            universal_message = communicator.get_universal_message()
            if universal_message is not None:
                print(f"Jetson pulse: {timestamp}")
                print(f'Received universal message: \n{universal_message}')
            else:
                print('No universal message received.')
            
    except KeyboardInterrupt:
        print("\nCtrl+C received.")
    finally:
        communicator.close()
