"""Scenarios for event retention during explicit evaluation."""

import unittest

from monitors import MonitoringService
from store import Store


class RetentionTests(unittest.TestCase):
    def test_cleanup_keeps_current_metrics(self):
        service = MonitoringService()
        service.create_monitor(10, 0.5)
        service.store.add_event(90, "example", 500)
        service.store.add_event(95, "example", 200)
        result = service.evaluate(1, 100)
        self.assertEqual([event.timestamp for event in service.store.events], [95])
        self.assertEqual(result["last_evaluation"], {
            "now": 100, "total": 1, "errors": 0, "error_fraction": 0.0,
        })
        self.assertEqual(service.evaluate(1, 100), result)

    def test_recent_out_of_order_events_are_usable(self):
        service = MonitoringService()
        service.create_monitor(10, 0.5)
        service.store.add_event(99, "example", 200)
        service.store.add_event(95, "example", 500)
        result = service.evaluate(1, 100)
        self.assertEqual(result["last_evaluation"]["total"], 2)
        self.assertEqual(result["last_evaluation"]["error_fraction"], 0.5)

    def test_shared_evaluation_time_is_nondecreasing(self):
        service = MonitoringService()
        service.create_monitor(10, 0.5)
        service.create_monitor(10, 0.5)
        service.evaluate(1, 100)
        with self.assertRaises(ValueError):
            service.evaluate(2, 99)
        self.assertEqual(service.inspect(2)["state"], "UNEVALUATED")
        self.assertEqual(service.evaluate(2, 100)["state"], "NO_DATA")

    def test_no_monitors_keep_available_history(self):
        store = Store()
        event = store.add_event(1, "example", 200)
        self.assertEqual(store.prune_events(100), 0)
        self.assertEqual(store.events, [event])


if __name__ == "__main__":
    unittest.main()
