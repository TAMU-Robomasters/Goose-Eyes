# Jetson AGX Orin HTE External Clock Setup

This document describes how we configured a Jetson AGX Orin to timestamp an external clock/PPS signal using Tegra HTE and expose those timestamps to Python through `/dev/hte_clock0`.

The goal is:

```text
External clock rising edge
        ↓
Jetson AGX Orin AON GPIO line 9 (pin 16)
        ↓
Tegra HTE hardware timestamp
        ↓
Custom kernel module
        ↓
/dev/hte_clock0
        ↓
Python repo reads timestamp events
```

---

# 1. Files changed / created checklist

## Device tree overlay

- [ ] `~/hte-test-overlay.dts`

Used to create a custom device-tree node:

```dts
hte_clock {
    compatible = "custom,hte-clock";
    in-gpios = <&gpio_aon 9 0>;
    timestamps = <&hte_aon 9>;
    timestamp-names = "external-clock";
};
```

## Compiled overlay

- [ ] `~/hte-test-overlay.dtbo`

Built from:

```bash
dtc -@ -I dts -O dtb \
  -o ~/hte-test-overlay.dtbo \
  ~/hte-test-overlay.dts
```

## Merged DTB

- [ ] `/boot/dtb/kernel_tegra234-p3737-0000+p3701-0005-nv-pio-hte.dtb`

Created with:

```bash
sudo fdtoverlay \
  -i /boot/dtb/kernel_tegra234-p3737-0000+p3701-0005-nv-pio.dtb \
  -o /boot/dtb/kernel_tegra234-p3737-0000+p3701-0005-nv-pio-hte.dtb \
  ~/hte-test-overlay.dtbo
```

## Boot config

- [ ] `/boot/extlinux/extlinux.conf`

Updated so the active boot entry uses:

```text
FDT /boot/dtb/kernel_tegra234-p3737-0000+p3701-0005-nv-pio-hte.dtb
```

## Custom kernel driver source

- [ ] `~/hte-clock-driver/hte-clock.c`

Custom HTE consumer driver. It:

- binds to `compatible = "custom,hte-clock"`
- reads the HTE timestamp line from device tree
- configures GPIO IRQ as rising edge
- receives HTE timestamp callbacks
- stores timestamp events in a FIFO
- exposes `/dev/hte_clock0`

## Kernel module Makefile

- [ ] `~/hte-clock-driver/Makefile`

Used to build the out-of-tree kernel module.

## Built kernel module

- [ ] `~/hte-clock-driver/hte-clock.ko`

Built with:

```bash
cd ~/hte-clock-driver
make clean
make
```

## Python reader

- [ ] `read_hte_clock.py`

Python test program that reads binary timestamp events from:

```text
/dev/hte_clock0
```

## Optional udev rule

- [ ] `/etc/udev/rules.d/99-hte-clock.rules`

Used to allow non-root access to `/dev/hte_clock0`.

Example:

```text
KERNEL=="hte_clock0", MODE="0666"
```

or group-based:

```text
KERNEL=="hte_clock0", GROUP="gpio", MODE="0660"
```

---

# 2. Hardware signal

The external clock/PPS signal is connected to Jetson AGX Orin 40-pin header pin 16.

On this system, that pin corresponds to AON GPIO offset:

```text
AON GPIO line 9
```

We confirmed this by observing the line toggle high/low and by successfully receiving HTE timestamps from the NVIDIA HTE test driver.

The working HTE test output looked like:

```text
HW timestamp(9: 136): 196344937216, edge: rising
```

Meaning:

```text
GPIO/HTE line: 9
sequence:      136
timestamp_ns:  196344937216
edge:          rising
```

---

# 3. Initial validation using NVIDIA HTE test driver

Before writing the custom driver, HTE was validated using NVIDIA's test driver:

```bash
sudo modprobe hte-tegra194-test
```

The test overlay used:

```dts
compatible = "nvidia,tegra194-hte-test";
```

and required both:

```dts
in-gpios = <&gpio_aon 9 0>;
out-gpios = <&gpio_aon XX 0>;
```

The `out-gpios` property was required by the NVIDIA test driver even though the real application only needs an input clock.

When working, `dmesg` showed:

```text
HW timestamp(9: 27): 185548230720, edge: rising
HW timestamp(9: 28): 186548238080, edge: rising
HW timestamp(9: 29): 187548245440, edge: rising
```

This proved:

- the pinmux was correct,
- GPIO line 9 was correct,
- the HTE provider worked,
- rising-edge timestamps were being generated.

---

# 4. Final custom device-tree overlay

The final application overlay uses a custom compatible string instead of the NVIDIA test driver.

File:

```text
~/hte-test-overlay.dts
```

Contents:

```dts
/dts-v1/;
/plugin/;

/ {
    compatible = "nvidia,p3737-0000+p3701-0005",
                 "nvidia,p3701-0005",
                 "nvidia,tegra234";

    fragment@0 {
        target-path = "/";
        __overlay__ {
            hte_clock {
                compatible = "custom,hte-clock";
                status = "okay";

                /*
                 * External clock input.
                 * Confirmed AON GPIO offset 9.
                 */
                in-gpios = <&gpio_aon 9 0>;

                /*
                 * HTE timestamp source for same GPIO.
                 */
                timestamps = <&hte_aon 9>;
                timestamp-names = "external-clock";
            };
        };
    };
};
```

Compile:

```bash
dtc -@ -I dts -O dtb \
  -o ~/hte-test-overlay.dtbo \
  ~/hte-test-overlay.dts
```

Apply to the base DTB:

```bash
sudo fdtoverlay \
  -i /boot/dtb/kernel_tegra234-p3737-0000+p3701-0005-nv-pio.dtb \
  -o /boot/dtb/kernel_tegra234-p3737-0000+p3701-0005-nv-pio-hte.dtb \
  ~/hte-test-overlay.dtbo
```

---

# 5. Boot configuration

The Jetson was configured to boot the merged DTB.

File:

```text
/boot/extlinux/extlinux.conf
```

The active boot entry should include:

```text
FDT /boot/dtb/kernel_tegra234-p3737-0000+p3701-0005-nv-pio-hte.dtb
```

Example:

```text
LABEL primary
      MENU LABEL primary kernel
      LINUX /boot/Image
      INITRD /boot/initrd
      FDT /boot/dtb/kernel_tegra234-p3737-0000+p3701-0005-nv-pio-hte.dtb
      APPEND ${cbootargs}
```

After editing:

```bash
sudo reboot
```

Verify the running device tree:

```bash
sudo dtc -I fs -O dts /proc/device-tree > /tmp/running.dts
grep -n -A25 -B5 "hte_clock" /tmp/running.dts
```

Expected relevant output:

```dts
hte_clock {
        timestamp-names = "external-clock";
        timestamps = <... 0x09>;
        compatible = "custom,hte-clock";
        status = "okay";
        in-gpios = <... 0x09 0x00>;
};
```

The many warnings from `dtc` when dumping `/proc/device-tree` are normal and were ignored.

---

# 6. Kernel driver

The custom kernel module is located at:

```text
~/hte-clock-driver/hte-clock.c
```

It creates:

```text
/dev/hte_clock0
```

The driver binds to:

```dts
compatible = "custom,hte-clock";
```

The driver:

1. Requests `in-gpios`.
2. Converts the GPIO to an IRQ.
3. Configures the IRQ as rising-edge.
4. Gets the HTE descriptor from the `timestamps` property.
5. Initializes HTE line attributes with `hte_init_line_attr()`.
6. Requests HTE timestamp callbacks.
7. Enables HTE timestamping.
8. Pushes timestamp records into a FIFO.
9. Exposes timestamp records through `/dev/hte_clock0`.

The event layout exported to Python is:

```c
struct hte_clock_event {
    __u64 timestamp_ns;
    __u64 sequence;
    __u32 gpio;
    __u32 edge;
};
```

Python reads this with:

```python
FMT = "<QQII"
```

The final working driver used:

```c
irq_set_irq_type(priv->irq, IRQ_TYPE_EDGE_RISING);
```

and:

```c
hte_init_line_attr(&priv->desc,
                   priv->desc.attr.line_id,
                   HTE_EDGE_NO_SETUP,
                   "external-clock",
                   priv->in_gpio);
```

This was important because directly setting only:

```c
priv->desc.attr.edge_flags = HTE_RISING_EDGE_TS;
```

or:

```c
priv->desc.attr.edge_flags = HTE_EDGE_NO_SETUP;
```

was not enough on this kernel.

---

# 7. Kernel module Makefile

File:

```text
~/hte-clock-driver/Makefile
```

Contents:

```make
obj-m += hte-clock.o

KDIR ?= /lib/modules/$(shell uname -r)/build

all:
    $(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
    $(MAKE) -C $(KDIR) M=$(PWD) clean
```

Important: the command lines under `all:` and `clean:` must start with a real tab.

Build:

```bash
cd ~/hte-clock-driver
make clean
make
```

Expected output includes:

```text
CC [M]  /home/orin/hte-clock-driver/hte-clock.o
MODPOST /home/orin/hte-clock-driver/Module.symvers
LD [M]  /home/orin/hte-clock-driver/hte-clock.ko
```

A warning like this is normal and harmless:

```text
warning: the compiler differs from the one used to build the kernel
```

---

# 8. Loading the custom module

Before loading the custom driver, make sure the NVIDIA test driver is not loaded:

```bash
sudo modprobe -r hte-tegra194-test 2>/dev/null
```

Unload an old custom module if needed:

```bash
sudo rmmod hte_clock 2>/dev/null
```

Load the custom module:

```bash
sudo insmod ~/hte-clock-driver/hte-clock.ko
```

Check logs:

```bash
sudo dmesg | grep -i "hte\|clock\|gpio" | tail -120
```

Expected successful messages:

```text
hte-clock hte_clock: input gpio irq=310
hte-clock hte_clock: requesting HTE line_id=9 edge_flags=1 line_data=...
hte-clock hte_clock: registered /dev/hte_clock0 for rising-edge HTE line 9
```

Check the device node:

```bash
ls -l /dev/hte_clock0
```

Expected:

```text
crw------- 1 root root ... /dev/hte_clock0
```

---

# 9. Python reader

File:

```text
read_hte_clock.py
```

Example:

```python
#!/usr/bin/env python3

import os
import struct
import select
import time

DEV = "/dev/hte_clock0"

# Matches:
#
# struct hte_clock_event {
#     __u64 timestamp_ns;
#     __u64 sequence;
#     __u32 gpio;
#     __u32 edge;
# };
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

    last_ts = None

    for event in read_events():
        now_mono_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)

        if last_ts is not None:
            period_ns = event.timestamp_ns - last_ts
            freq_hz = 1_000_000_000.0 / period_ns if period_ns > 0 else 0.0
        else:
            period_ns = None
            freq_hz = None

        last_ts = event.timestamp_ns

        print(
            f"event: gpio={event.gpio} "
            f"seq={event.sequence} "
            f"timestamp_ns={event.timestamp_ns} "
            f"edge={event.edge_name} "
            f"period_ns={period_ns} "
            f"freq_hz={freq_hz} "
            f"python_mono_raw_ns={now_mono_ns}"
        )


if __name__ == "__main__":
    main()
```

Run with root initially:

```bash
sudo python3 read_hte_clock.py
```

or from the repo:

```bash
sudo uv run read_hte_clock.py
```

If working, output looks like:

```text
Opening /dev/hte_clock0
Event size: 24 bytes
Waiting for rising-edge HTE events...
event: gpio=9 seq=1 timestamp_ns=123456789000 edge=rising period_ns=None freq_hz=None python_mono_raw_ns=...
event: gpio=9 seq=2 timestamp_ns=124456796360 edge=rising period_ns=1000007360 freq_hz=0.9999926400541692 python_mono_raw_ns=...
```

---

# 10. Permissions for non-root Python

Initially, running without sudo may fail:

```text
PermissionError: [Errno 13] Permission denied: '/dev/hte_clock0'
```

Quick test:

```bash
sudo python3 read_hte_clock.py
```

Permanent simple permission rule:

```bash
sudo nano /etc/udev/rules.d/99-hte-clock.rules
```

Add:

```text
KERNEL=="hte_clock0", MODE="0666"
```

Reload udev:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Recreate the device node:

```bash
sudo rmmod hte_clock
sudo insmod ~/hte-clock-driver/hte-clock.ko
```

Check:

```bash
ls -l /dev/hte_clock0
```

Expected:

```text
crw-rw-rw- 1 root root ... /dev/hte_clock0
```

Then Python can run without sudo:

```bash
uv run read_hte_clock.py
```

A more secure option is group-based access:

```bash
sudo groupadd -f gpio
sudo usermod -aG gpio $USER
```

udev rule:

```text
KERNEL=="hte_clock0", GROUP="gpio", MODE="0660"
```

Then log out/in or reboot.

---

# 11. Troubleshooting notes

## Module signature warning

This is normal for an out-of-tree module:

```text
hte_clock: module verification failed: signature and/or required key missing - tainting kernel
```

It does not prevent the driver from working.

## Device missing

If this fails:

```bash
ls -l /dev/hte_clock0
```

with:

```text
No such file or directory
```

check:

```bash
sudo dmesg | grep -i "hte\|clock\|gpio" | tail -120
```

The module likely failed during probe.

## Wrong overlay active

Check running DT:

```bash
sudo dtc -I fs -O dts /proc/device-tree > /tmp/running.dts
grep -n -A25 -B5 "hte_clock\|hte_gpio_test" /tmp/running.dts
```

For the custom driver, you want:

```dts
compatible = "custom,hte-clock";
```

For NVIDIA dmesg test mode, you would see:

```dts
compatible = "nvidia,tegra194-hte-test";
```

Do not use both at the same time.

## HTE request failed

Earlier failed attempts showed:

```text
tegra_hte c1e0000.hardware-timestamp: failed to request id: 9
hte-clock hte_clock: failed to request HTE timestamps: -22
```

The fix was to match the HTE setup expected by this kernel:

```c
irq_set_irq_type(priv->irq, IRQ_TYPE_EDGE_RISING);
```

and:

```c
hte_init_line_attr(&priv->desc,
                   priv->desc.attr.line_id,
                   HTE_EDGE_NO_SETUP,
                   "external-clock",
                   priv->in_gpio);
```

## Test driver vs custom driver

NVIDIA test driver:

```dts
compatible = "nvidia,tegra194-hte-test";
```

prints to:

```text
dmesg
```

Custom driver:

```dts
compatible = "custom,hte-clock";
```

exports:

```text
/dev/hte_clock0
```

The custom driver does not print every timestamp to `dmesg`; Python reads them from `/dev/hte_clock0`.

---

# 12. Useful commands

Build module:

```bash
cd ~/hte-clock-driver
make clean
make
```

Load module:

```bash
sudo modprobe -r hte-tegra194-test 2>/dev/null
sudo rmmod hte_clock 2>/dev/null
sudo insmod ~/hte-clock-driver/hte-clock.ko
```

Check logs:

```bash
sudo dmesg | grep -i "hte\|clock\|gpio" | tail -120
```

Check device:

```bash
ls -l /dev/hte_clock0
```

Run Python reader:

```bash
sudo python3 read_hte_clock.py
```

or:

```bash
uv run read_hte_clock.py
```

if udev permissions are configured.

Check running DT:

```bash
sudo dtc -I fs -O dts /proc/device-tree > /tmp/running.dts
grep -n -A25 -B5 "hte_clock" /tmp/running.dts
```

Rebuild overlay:

```bash
dtc -@ -I dts -O dtb \
  -o ~/hte-test-overlay.dtbo \
  ~/hte-test-overlay.dts
```

Apply overlay to DTB:

```bash
sudo fdtoverlay \
  -i /boot/dtb/kernel_tegra234-p3737-0000+p3701-0005-nv-pio.dtb \
  -o /boot/dtb/kernel_tegra234-p3737-0000+p3701-0005-nv-pio-hte.dtb \
  ~/hte-test-overlay.dtbo
```

---

# 13. Summary

The final working setup uses:

```text
GPIO AON line 9
```

with Tegra HTE timestamps.

The application path is:

```text
external rising edge
    -> Tegra HTE timestamp
    -> hte-clock.ko callback
    -> kernel FIFO
    -> /dev/hte_clock0
    -> Python read_hte_clock.py
```

This avoids parsing `dmesg` and gives the Python repo structured timestamp data suitable for syncing an internal timer to an external reference clock.