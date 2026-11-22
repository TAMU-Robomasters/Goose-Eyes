import threading
from bisect import bisect_left, bisect_right

DEFAULT_WINDOW_NS = 500_000_000
DEFAULT_MAX_GAP_NS = 100_000_000


class PulseBuffer:
    def __init__(self, window_ns=DEFAULT_WINDOW_NS, max_gap_ns=DEFAULT_MAX_GAP_NS):
        self.window_ns = window_ns
        self.max_gap_ns = max_gap_ns

        self._times = []
        self._pulses = []
        self._start = 0

        self.rejected = 0
        self._lock = threading.Lock()

    def add(self, jetson_ns, pulse):
        with self._lock:
            return self._add_locked(jetson_ns, pulse)

    def add_many(self, entries):
        with self._lock:
            for jetson_ns, pulse in entries:
                self._add_locked(jetson_ns, pulse)

    def prune(self, now_ns):
        with self._lock:
            self._prune_locked(now_ns - self.window_ns)

    def clear(self):
        with self._lock:
            self._times.clear()
            self._pulses.clear()
            self._start = 0

    def _add_locked(self, jetson_ns, pulse):
        if len(self._times) > self._start and (
            jetson_ns <= self._times[-1] or pulse <= self._pulses[-1]
        ):
            self.rejected += 1
            return False

        self._times.append(jetson_ns)
        self._pulses.append(pulse)
        self._prune_locked(jetson_ns - self.window_ns)
        return True

    def _prune_locked(self, cutoff_ns):
        self._start = bisect_left(self._times, cutoff_ns, lo=self._start)

        if self._start and self._start * 2 >= len(self._times):
            del self._times[: self._start]
            del self._pulses[: self._start]
            self._start = 0

    def __len__(self):
        with self._lock:
            return len(self._times) - self._start

    def snapshot(self):
        with self._lock:
            return list(zip(self._times[self._start :], self._pulses[self._start :]))

    def pulse_to_time(self, pulse):
        with self._lock:
            i = self._floor_index(self._pulses, pulse)
            return None if i is None else self._times[i]

    def time_to_pulse(self, jetson_ns):
        with self._lock:
            i = self._floor_index(self._times, jetson_ns)
            return None if i is None else self._pulses[i]

    def pulse_to_time_interp(self, pulse):
        with self._lock:
            pair = self._bracket(self._pulses, pulse)
            if pair is None:
                return None
            lo, hi = pair
            t0, t1 = self._times[lo], self._times[hi]
            p0, p1 = self._pulses[lo], self._pulses[hi]
            if lo == hi:
                return t0
            return round(t0 + (t1 - t0) * (pulse - p0) / (p1 - p0))

    def time_to_pulse_interp(self, jetson_ns):
        with self._lock:
            pair = self._bracket(self._times, jetson_ns)
            if pair is None:
                return None
            lo, hi = pair
            t0, t1 = self._times[lo], self._times[hi]
            p0, p1 = self._pulses[lo], self._pulses[hi]
            if lo == hi:
                return float(p0)
            return p0 + (p1 - p0) * (jetson_ns - t0) / (t1 - t0)

    def _floor_index(self, column, value):
        end = len(column)
        if end == self._start or value < column[self._start] or value > column[-1]:
            return None
        return bisect_right(column, value, lo=self._start) - 1

    def _bracket(self, column, value):
        i = self._floor_index(column, value)
        if i is None:
            return None
        if column[i] == value:
            return i, i
        lo, hi = i, i + 1
        if (
            self.max_gap_ns is not None
            and self._times[hi] - self._times[lo] > self.max_gap_ns
        ):
            return None
        return lo, hi
