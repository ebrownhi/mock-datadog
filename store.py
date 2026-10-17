"""In-memory records for a single running process."""

from dataclasses import dataclass, field
import math


def number(value, name, minimum=0):
    """Validate a finite int or float, excluding booleans, without coercion."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value < minimum:
        raise ValueError(f"{name} must be finite and at least {minimum}")
    return value


@dataclass(frozen=True)
class Event:
    """Immutable event record; timestamp is Unix seconds and service is trimmed."""

    timestamp: float
    service: str
    status: int


@dataclass
class Monitor:
    """Mutable monitor state, with separate dictionaries/lists for each instance.

    last_evaluation is empty until evaluated. incident_open survives NO_DATA,
    independently of state; history contains alert/recovery transition snapshots.
    """

    id: int
    window_seconds: float
    threshold: float
    state: str = "UNEVALUATED"
    incident_open: bool = False
    last_evaluation: dict = field(default_factory=dict)
    history: list = field(default_factory=list)


class Store:
    """Retain unsorted events and monitors with process-local increasing IDs."""

    def __init__(self):
        self.events = []
        self.monitors = {}
        self.next_monitor_id = 1

    def add_event(self, timestamp, service, status):
        number(timestamp, "timestamp")
        if not isinstance(service, str) or not service.strip() or len(service) > 100:
            raise ValueError("service must be a nonempty string of at most 100 characters")
        if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
            raise ValueError("status must be an integer from 100 to 599")
        event = Event(timestamp, service.strip(), status)
        self.events.append(event)
        return event

    def add_monitor(self, window_seconds, threshold):
        number(window_seconds, "window_seconds")
        number(threshold, "threshold")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be greater than zero")
        if not 0 < threshold <= 1:
            raise ValueError("threshold must be greater than zero and at most one")
        monitor = Monitor(self.next_monitor_id, window_seconds, threshold)
        self.monitors[monitor.id] = monitor
        self.next_monitor_id += 1
        return monitor

    def get_monitor(self, monitor_id):
        if monitor_id not in self.monitors:
            raise KeyError("monitor not found")
        return self.monitors[monitor_id]
