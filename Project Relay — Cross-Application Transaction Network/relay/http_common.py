import hmac
import json
import os
from http.server import BaseHTTPRequestHandler

MAX_BODY = 16384


def required_secret(name):
    value = os.environ.get(name, "")
    if len(value) < 32:
        raise ValueError(f"{name} must be at least 32 characters")
    return value.encode()


def signature(key, body):
    return hmac.digest(key, body, "sha256").hex()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def reply(self, status, value):
        body = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise ValueError("application/json required")
        size = int(self.headers.get("Content-Length", "0"))
        if size < 1 or size > MAX_BODY:
            raise ValueError("Invalid body length")
        data = self.rfile.read(size)
        if len(data) != size:
            raise ValueError("Incomplete body")
        return data

    def authorized(self, secret):
        provided = self.headers.get("Authorization", "").encode()
        return hmac.compare_digest(provided, b"Bearer " + secret)
