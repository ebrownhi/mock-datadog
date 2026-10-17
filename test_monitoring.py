import json
import threading
import unittest
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import dispatch, make_handler
from monitors import MonitoringService
from metrics import legacy_bucket_rates, summarize
from store import Event


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.service = MonitoringService()
        self.service.create_monitor(10, 0.5)

    def event(self, timestamp, status, service="example"):
        self.service.store.add_event(timestamp, service, status)

    def test_window_boundaries_and_error_definition(self):
        for timestamp, status in [(90, 500), (91, 499), (100, 599), (101, 500)]:
            self.event(timestamp, status)
        result = self.service.evaluate(1, 100)
        self.assertEqual(result["last_evaluation"], {
            "now": 100, "total": 2, "errors": 1, "error_fraction": 0.5,
        })
        self.assertEqual(result["state"], "ALERT")

    def test_empty_and_healthy_are_distinct(self):
        self.assertEqual(self.service.inspect(1)["state"], "UNEVALUATED")
        empty = self.service.evaluate(1, 100)
        self.assertEqual(empty["state"], "NO_DATA")
        self.assertIsNone(empty["last_evaluation"]["error_fraction"])
        self.event(100, 200)
        healthy = self.service.evaluate(1, 100)
        self.assertEqual(healthy["state"], "OK")
        self.assertEqual(healthy["last_evaluation"]["error_fraction"], 0)
        self.assertEqual(healthy["history"], [])

    def test_alert_recovery_and_no_duplicate_notifications(self):
        self.event(100, 500)
        self.service.evaluate(1, 100)
        self.service.evaluate(1, 100)
        empty = self.service.evaluate(1, 111)
        self.assertEqual(empty["state"], "NO_DATA")
        self.assertTrue(empty["incident_open"])
        self.event(112, 500)
        still_open = self.service.evaluate(1, 112)
        self.assertEqual(len(still_open["history"]), 1)
        self.event(123, 200)
        self.service.evaluate(1, 123)
        recovered = self.service.evaluate(1, 123)
        self.assertFalse(recovered["incident_open"])
        self.assertEqual([entry["kind"] for entry in recovered["history"]],
                         ["ALERT", "RECOVERY"])
        self.event(134, 503)
        self.assertEqual(len(self.service.evaluate(1, 134)["history"]), 3)

    def test_monitors_are_independent_and_count_all_services(self):
        self.service.create_monitor(10, 0.75)
        self.event(100, 500, "alpha")
        self.event(100, 200, "beta")
        self.assertEqual(self.service.evaluate(1, 100)["state"], "ALERT")
        self.assertEqual(self.service.inspect(2)["state"], "UNEVALUATED")
        self.assertEqual(self.service.evaluate(2, 100)["state"], "OK")
        snapshot = self.service.inspect(1)
        snapshot["history"].clear()
        self.assertEqual(len(self.service.inspect(1)["history"]), 1)

    def test_evaluation_time_cannot_move_backwards(self):
        self.service.evaluate(1, 100)
        with self.assertRaises(ValueError):
            self.service.evaluate(1, 99)

    def test_api_validation(self):
        cases = [
            ("/events", {}),
            ("/events", []),
            ("/events", {"timestamp": 1, "service": " ", "status": 200}),
            ("/events", {"timestamp": -1, "service": "a", "status": 200}),
            ("/events", {"timestamp": True, "service": "a", "status": 200}),
            ("/events", {"timestamp": 1, "service": "a", "status": 600}),
            ("/events", {"timestamp": 1, "service": "a", "status": 200.0}),
            ("/monitors", {"window_seconds": 0, "threshold": 0.5}),
            ("/monitors", {"window_seconds": 10, "threshold": 0}),
            ("/monitors", {"window_seconds": 10, "threshold": 1.1}),
            ("/monitors", {"window_seconds": float("inf"), "threshold": 0.5}),
            ("/monitors/1/evaluate", {"now": float("nan")}),
            ("/monitors/1/evaluate", {"now": "100"}),
            ("/monitors/1/evaluate", {"extra": 1}),
        ]
        for path, body in cases:
            with self.subTest(path=path, body=body):
                status, payload = dispatch(self.service, "POST", path, body)
                self.assertEqual(status, 400)
                self.assertIn("error", payload)
        self.assertEqual(len(self.service.store.events), 0)
        self.assertEqual(len(self.service.store.monitors), 1)
        self.assertEqual(dispatch(self.service, "GET", "/monitors/99")[0], 404)
        self.assertEqual(dispatch(self.service, "GET", "/missing")[0], 404)

    def test_api_uses_injected_clock(self):
        status, result = dispatch(self.service, "POST", "/monitors/1/evaluate",
                                  {}, clock=lambda: 123)
        self.assertEqual(status, 200)
        self.assertEqual(result["last_evaluation"]["now"], 123)


class LegacyBucketTests(unittest.TestCase):
    def test_epoch_aligned_boundaries_and_sorted_output(self):
        events = [Event(120, "example", 200), Event(59.5, "example", 500),
                  Event(60, "example", 503), Event(0, "example", 200)]
        self.assertEqual(legacy_bucket_rates(events, 60), [
            {"start": 0, "end": 60, "total": 2, "errors": 1, "error_fraction": 0.5},
            {"start": 60, "end": 120, "total": 1, "errors": 1, "error_fraction": 1.0},
            {"start": 120, "end": 180, "total": 1, "errors": 0, "error_fraction": 0.0},
        ])

    def test_rates_count_only_5xx_and_omit_empty_buckets(self):
        events = [Event(1, "alpha", 499), Event(2, "beta", 500),
                  Event(3, "alpha", 599), Event(180, "beta", 200)]
        buckets = legacy_bucket_rates(events)
        self.assertEqual([bucket["start"] for bucket in buckets], [0, 180])
        self.assertEqual(buckets[0]["total"], 3)
        self.assertEqual(buckets[0]["errors"], 2)
        self.assertAlmostEqual(buckets[0]["error_fraction"], 2 / 3)
        self.assertEqual(buckets[1]["error_fraction"], 0.0)

    def test_empty_input_has_no_buckets(self):
        self.assertEqual(legacy_bucket_rates([]), [])

    def test_fixed_buckets_differ_from_rolling_window(self):
        events = [Event(60, "example", 500), Event(90, "example", 200)]
        # At 90, rolling (30, 90] includes both requests. Fixed [60, 90)
        # excludes the request at 90, which belongs to [90, 120).
        self.assertEqual(summarize(events, 60, 90)["error_fraction"], 0.5)
        buckets = legacy_bucket_rates(events, 30)
        self.assertEqual([bucket["error_fraction"] for bucket in buckets], [1.0, 0.0])

    def test_invalid_bucket_size(self):
        for size in (0, -1, True, 1.5, "60", float("inf")):
            with self.subTest(size=size), self.assertRaises(ValueError):
                legacy_bucket_rates([], size)


class HttpTests(unittest.TestCase):
    def test_json_transport(self):
        server = HTTPServer(("127.0.0.1", 0), make_handler(MonitoringService()))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = "http://127.0.0.1:" + str(server.server_port)
            with urlopen(url + "/health", timeout=2) as response:
                self.assertEqual(json.load(response), {"status": "ok"})
            request = Request(url + "/events", data=b"{broken", method="POST")
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=2)
            self.assertEqual(caught.exception.code, 400)
            self.assertIn("error", json.load(caught.exception))
            caught.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
