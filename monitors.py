"""Evaluate monitors and record alert lifecycle transitions."""

from dataclasses import asdict

from metrics import summarize
from store import Store, number


class MonitoringService:
    def __init__(self, store=None):
        self.store = store if store is not None else Store()

    def create_monitor(self, window_seconds, threshold):
        return asdict(self.store.add_monitor(window_seconds, threshold))

    def inspect(self, monitor_id):
        """Return a detached snapshot so callers cannot mutate stored state."""
        return asdict(self.store.get_monitor(monitor_id))

    def evaluate(self, monitor_id, now):
        """Recompute global metrics and update this monitor at nondecreasing now.

        The incident flag controls transition recording: NO_DATA preserves it,
        ALERT opens it once, and OK closes it once. asdict returns a snapshot.
        """
        number(now, "now")
        monitor = self.store.get_monitor(monitor_id)
        previous_now = monitor.last_evaluation.get("now")
        if previous_now is not None and now < previous_now:
            raise ValueError("now must not precede this monitor's last evaluation")
        self.store.prune_events(now)
        summary = summarize(self.store.events, monitor.window_seconds, now)
        fraction = summary["error_fraction"]
        if fraction is None:
            state = "NO_DATA"
        elif fraction >= monitor.threshold:
            state = "ALERT"
        else:
            state = "OK"

        if state == "ALERT" and not monitor.incident_open:
            monitor.history.append({"kind": "ALERT", "timestamp": now, **summary})
            monitor.incident_open = True
        elif state == "OK" and monitor.incident_open:
            monitor.history.append({"kind": "RECOVERY", "timestamp": now, **summary})
            monitor.incident_open = False
        monitor.state = state
        monitor.last_evaluation = {"now": now, **summary}
        return asdict(monitor)
