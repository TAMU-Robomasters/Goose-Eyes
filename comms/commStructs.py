import struct
from dataclasses import dataclass

# Request numbers
REQUEST_RESET = 0
REQUEST_GIMBAL_POS = 1


@dataclass
class QueryPacket:
    """
    Packet sent from Jetson/PC to dev board.

    Binary layout, little-endian:

        uint32 timestamp
        uint8  requestNumber

    Total size: 5 bytes
    """

    timestamp: int
    requestNumber: int

    _FORMAT = "<IB"
    SIZE = struct.calcsize(_FORMAT)

    def pack(self) -> bytes:
        return struct.pack(self._FORMAT, self.timestamp, self.requestNumber)

    @classmethod
    def unpack(cls, data: bytes) -> "QueryPacket":
        if len(data) != cls.SIZE:
            raise ValueError(f"QueryPacket requires {cls.SIZE} bytes, got {len(data)}")

        timestamp, requestNumber = struct.unpack(cls._FORMAT, data)

        return cls(timestamp=timestamp, requestNumber=requestNumber)


@dataclass
class GimbalPacket:
    """
    Packet sent from dev board to Jetson/PC.

    Binary layout, little-endian:

        uint32 timestamp
        float  yaw
        float  pitch

    Total size: 12 bytes
    """

    timestamp: int
    yaw: float
    pitch: float

    _FORMAT = "<Iff"
    SIZE = struct.calcsize(_FORMAT)

    def pack(self) -> bytes:
        return struct.pack(self._FORMAT, self.timestamp, self.yaw, self.pitch)

    @classmethod
    def unpack(cls, data: bytes) -> "GimbalPacket":
        if len(data) != cls.SIZE:
            raise ValueError(f"GimbalPacket requires {cls.SIZE} bytes, got {len(data)}")

        timestamp, yaw, pitch = struct.unpack(cls._FORMAT, data)

        return cls(timestamp=timestamp, yaw=yaw, pitch=pitch)
