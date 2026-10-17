"""A deterministic API integration scenario, without starting an HTTP server."""

import unittest

from app import dispatch
from monitors import MonitoringService


class ApiScenarioTests(unittest.TestCase):
    def setUp(self):
        self.service = MonitoringService()

    def request(self, method, path, body=None, expected_status=200):
        status, payload = dispatch(self.service, method, path, body)
        self.assertEqual(status, expected_status, payload)
        return payload

    def test_monitor_alerts_and_recovers(self):
        self.assertEqual(self.request("GET", "/health"), {"status": "ok"})
        monitor = self.request("POST", "/monitors", {
            "window_seconds": 60, "threshold": 0.5,
        }, expected_status=201)
        self.assertEqual(monitor["state"], "UNEVALUATED")
        monitor_path = f"/monitors/{monitor['id']}"

        failed_event = {"timestamp": 1000, "service": "example", "status": 503}
        self.assertEqual(self.request("POST", "/events", failed_event,
                                      expected_status=201), failed_event)
        alert = self.request("POST", monitor_path + "/evaluate", {"now": 1000})
        self.assertEqual(alert["state"], "ALERT")
        self.assertTrue(alert["incident_open"])
        self.assertEqual(alert["last_evaluation"], {
            "now": 1000, "total": 1, "errors": 1, "error_fraction": 1.0,
        })
        self.assertEqual(alert["history"], [{
            "kind": "ALERT", "timestamp": 1000,
            "total": 1, "errors": 1, "error_fraction": 1.0,
        }])
        self.assertEqual(self.request("GET", monitor_path), alert)

        # The failed request has left the 60-second window by time 1061.
        healthy_event = {"timestamp": 1061, "service": "example", "status": 200}
        self.assertEqual(self.request("POST", "/events", healthy_event,
                                      expected_status=201), healthy_event)
        recovery = self.request("POST", monitor_path + "/evaluate", {"now": 1061})
        self.assertEqual(recovery["state"], "OK")
        self.assertFalse(recovery["incident_open"])
        self.assertEqual(recovery["last_evaluation"], {
            "now": 1061, "total": 1, "errors": 0, "error_fraction": 0.0,
        })
        self.assertEqual(recovery["history"], alert["history"] + [{
            "kind": "RECOVERY", "timestamp": 1061,
            "total": 1, "errors": 0, "error_fraction": 0.0,
        }])
        self.assertEqual(self.request("GET", monitor_path), recovery)


if __name__ == "__main__":
    unittest.main()
