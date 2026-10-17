"""Small JSON HTTP interface. Run with python3 app.py."""

import json
import re
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer

from monitors import MonitoringService


def fields(body, required, optional=()):
    """Check object shape before domain validation; reject unknown fields."""
    if not isinstance(body, dict):
        raise ValueError("body must be a JSON object")
    missing = set(required) - body.keys()
    extra = body.keys() - set(required) - set(optional)
    if missing or extra:
        raise ValueError("expected fields: " + ", ".join(required + tuple(optional)))


def dispatch(service, method, path, body=None, clock=time.time):
    """Route decoded payloads and return (HTTP status, JSON-compatible payload).

    Use the injected clock only when evaluation omits now. Domain validation
    and missing-monitor errors become API responses here.
    """
    try:
        if method == "GET" and path == "/health":
            return 200, {"status": "ok"}
        if method == "POST" and path == "/events":
            fields(body, ("timestamp", "service", "status"))
            return 201, asdict(service.store.add_event(**body))
        if method == "POST" and path == "/monitors":
            fields(body, ("window_seconds", "threshold"))
            return 201, service.create_monitor(**body)
        match = re.fullmatch(r"/monitors/([1-9][0-9]*)(/evaluate)?", path)
        if match:
            monitor_id = int(match.group(1))
            if method == "GET" and not match.group(2):
                return 200, service.inspect(monitor_id)
            if method == "POST" and match.group(2):
                fields(body, (), ("now",))
                now = body["now"] if "now" in body else clock()
                return 200, service.evaluate(monitor_id, now)
        return 404, {"error": "route not found"}
    except ValueError as error:
        return 400, {"error": str(error)}
    except KeyError:
        return 404, {"error": "monitor not found"}


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, payload):
            encoded = json.dumps(payload, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            self.respond(*dispatch(service, "GET", self.path))

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("body size must be between 1 and 65536 bytes")
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self.respond(400, {"error": "invalid JSON body or body size"})
                return
            self.respond(*dispatch(service, "POST", self.path, body))

    return Handler


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8000), make_handler(MonitoringService()))
    print("Listening on http://127.0.0.1:8000", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
