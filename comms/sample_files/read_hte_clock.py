#!/usr/bin/env python3

import os
import statistics
import struct
import select
import time
import matplotlib.pyplot as plt

DEV = "/dev/hte_clock0"

# Must match kernel struct:
#
# struct hte_clock_event {
#     __u64 timestamp_ns;
#     __u64 sequence;
#     __u32 gpio;
#     __u32 edge;
# };
#
# Little-endian:
# Q = uint64
# I = uint32
FMT = "<QQII"
EVENT_SIZE = struct.calcsize(FMT)


class HTEClockEvent:
    def __init__(self, timestamp_ns, sequence, gpio, edge):
        self.timestamp_ns = timestamp_ns
        self.sequence = sequence
        self.gpio = gpio
        self.edge = edge

    @property
    def edge_name(self):
        return "rising" if self.edge else "falling"

    def __repr__(self):
        return (
            f"HTEClockEvent("
            f"timestamp_ns={self.timestamp_ns}, "
            f"sequence={self.sequence}, "
            f"gpio={self.gpio}, "
            f"edge={self.edge_name})"
        )


def read_events(dev=DEV):
    fd = os.open(dev, os.O_RDONLY)

    try:
        poller = select.poll()
        poller.register(fd, select.POLLIN)

        while True:
            poller.poll()

            data = os.read(fd, EVENT_SIZE)

            if len(data) != EVENT_SIZE:
                print(f"short read: got {len(data)} bytes, expected {EVENT_SIZE}")
                continue

            timestamp_ns, sequence, gpio, edge = struct.unpack(FMT, data)

            yield HTEClockEvent(
                timestamp_ns=timestamp_ns,
                sequence=sequence,
                gpio=gpio,
                edge=edge,
            )

    finally:
        os.close(fd)


def main():
    print(f"Opening {DEV}")
    print(f"Event size: {EVENT_SIZE} bytes")
    print("Waiting for rising-edge HTE events...")

    test_time = 5 * 60e9
    last_ts = None
    start_time = time.perf_counter_ns()
    frequency_list = []
    for event in read_events():
        now_mono_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)

        if last_ts is not None:
            period_ns = event.timestamp_ns - last_ts
            freq_hz = 1_000_000_000.0 / period_ns if period_ns > 0 else 0.0
            frequency_list.append(freq_hz)
        else:
            period_ns = None
            freq_hz = None

        last_ts = event.timestamp_ns

        # print(
        #     f"event: gpio={event.gpio} "
        #     f"seq={event.sequence} "
        #     f"timestamp_ns={event.timestamp_ns} "
        #     f"edge={event.edge_name} "
        #     f"period_ns={period_ns} "
        #     f"freq_hz={freq_hz} "
        #     f"python_mono_raw_ns={now_mono_ns}"
        # )
        if time.perf_counter_ns() - start_time > test_time:
            break

    if frequency_list:
        frequency_list = frequency_list[len(frequency_list) // 10 :]
        mean_freq = statistics.mean(frequency_list)
        pop_std = statistics.pstdev(frequency_list)
        print(
            f"Mean: {mean_freq}, Population Std Dev: {pop_std}, Max: {max(frequency_list)}, Min: {min(frequency_list)}"
        )
        with open("data.txt", "a") as file:
            file.write(
                f"Mean: {mean_freq}, Mean Period: {1 / mean_freq if mean_freq > 0 else 0.0}, Population Std Dev: {pop_std}\n"
            )
        pulses = range(1, len(frequency_list) + 1)

        plt.figure()
        plt.plot(pulses, frequency_list)
        plt.xlabel("Pulse")
        plt.ylabel("Frequency Hz")
        plt.title("Frequency vs Pulse")
        plt.grid(True)
        plt.savefig("frequency_vs_pulse.png", dpi=150)
        plt.close()
    return


if __name__ == "__main__":
    main()
