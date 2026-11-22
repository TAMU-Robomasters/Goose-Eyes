import threading

from pulse_conversion import PulseBuffer

T0 = 1_000_000_000_000
PERIOD = 1_000


def make_buffer(n, step=1, start_pulse=100, **kwargs):
    buf = PulseBuffer(**kwargs)
    for k in range(n):
        p = start_pulse + k * step
        buf.add(T0 + (p - start_pulse) * PERIOD, p)
    return buf


def test_exact_lookup():
    buf = make_buffer(10)
    assert buf.pulse_to_time(100) == T0
    assert buf.pulse_to_time(105) == T0 + 5 * PERIOD
    assert buf.time_to_pulse(T0 + 5 * PERIOD) == 105


def test_non_interp_holds_previous_sample():
    buf = make_buffer(10, step=10)
    assert buf.pulse_to_time(115) == buf.pulse_to_time(110)
    assert buf.time_to_pulse(T0 + 15 * PERIOD) == 110


def test_out_of_range_is_none():
    buf = make_buffer(10)
    assert buf.pulse_to_time(99) is None
    assert buf.pulse_to_time(110) is None
    assert buf.pulse_to_time_interp(99) is None
    assert buf.time_to_pulse(T0 - 1) is None
    assert buf.time_to_pulse_interp(T0 + 100 * PERIOD) is None
    assert PulseBuffer().pulse_to_time(0) is None


def test_interp_between_samples():
    buf = make_buffer(10, step=10)
    assert buf.pulse_to_time_interp(115) == T0 + 15 * PERIOD
    assert buf.pulse_to_time_interp(112.5) == T0 + 12_500
    assert buf.time_to_pulse_interp(T0 + 15 * PERIOD) == 115.0
    assert buf.time_to_pulse_interp(T0 + 15_250) == 115.25


def test_interp_exact_hit_and_last_entry():
    buf = make_buffer(10)
    assert buf.pulse_to_time_interp(109) == T0 + 9 * PERIOD
    assert buf.time_to_pulse_interp(T0 + 9 * PERIOD) == 109.0


def test_window_drops_old_entries():
    buf = make_buffer(2000, step=1000)
    newest_t = T0 + 1999 * 1000 * PERIOD
    snap = buf.snapshot()
    assert snap[-1][0] == newest_t
    assert snap[0][0] >= newest_t - buf.window_ns
    assert len(buf) == 501
    assert buf.pulse_to_time(100) is None


def test_prune_with_external_now():
    buf = make_buffer(10)
    buf.prune(T0 + 9 * PERIOD + buf.window_ns + 1)
    assert len(buf) == 0


def test_rejects_out_of_order():
    buf = make_buffer(5)
    assert buf.add(T0, 200) is False
    assert buf.add(T0 + 10 * PERIOD, 104) is False
    assert buf.rejected == 2
    assert len(buf) == 5


def test_no_interp_across_large_gap():
    buf = PulseBuffer(max_gap_ns=100_000_000)
    buf.add(T0, 0)
    buf.add(T0 + 300_000_000, 1)
    assert buf.pulse_to_time_interp(0.5) is None
    assert buf.time_to_pulse_interp(T0 + 150_000_000) is None
    assert buf.pulse_to_time(0) == T0


def test_concurrent_writer_and_reader():
    buf = PulseBuffer()
    errors = []

    def writer():
        for k in range(20_000):
            buf.add(T0 + k * PERIOD, k)

    def reader():
        for _ in range(20_000):
            snap = buf.snapshot()
            if snap and buf.pulse_to_time(snap[0][1]) not in (snap[0][0], None):
                errors.append(snap[0])

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(buf) == 20_000


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print("ok  ", test.__name__)
    print(f"{len(tests)} passed")
