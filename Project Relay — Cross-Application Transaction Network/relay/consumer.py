"""Application-owned inbox service, instantiated independently for each receiving app."""
import hmac
import json
import os
import sqlite3
from http.server import ThreadingHTTPServer

from relay import store
from relay.http_common import Handler, required_secret, signature
from relay.model import TARGETS, validate


def handler(path, key, name):
    class Consumer(Handler):
        def do_GET(self):
            if self.path != "/healthz":
                return self.reply(404, {"error": "not found"})
            try:
                with store.connection(path) as db:
                    db.execute("SELECT id FROM inbox LIMIT 1").fetchone()
            except sqlite3.Error:
                return self.reply(503, {"status": "unavailable"})
            return self.reply(200, {"status": "ok", "application": name})

        def do_POST(self):
            if self.path != "/inbox":
                return self.reply(404, {"error": "not found"})
            try:
                raw = self.body()
            except (ValueError, UnicodeError):
                return self.reply(400, {"error": "invalid request"})
            provided = self.headers.get("X-Relay-Signature", "").encode()
            if not hmac.compare_digest(signature(key, raw).encode(), provided):
                return self.reply(401, {"error": "unauthorized"})
            try:
                event = validate(json.loads(raw))
                result = store.receive(path, event)
            except (ValueError, UnicodeError, TypeError):
                return self.reply(400, {"error": "invalid transaction"})
            except sqlite3.Error:
                return self.reply(503, {"error": "store unavailable"})
            if result == "conflict":
                return self.reply(409, {"error": "transaction conflict"})
            return self.reply(200, {"transaction_id": event["transaction_id"],
                                    "application": name, "status": result})

    return Consumer


def main():
    name = os.environ["APPLICATION_NAME"]
    if name not in TARGETS:
        raise ValueError("Unknown application name")
    path = os.environ.get("INBOX_DB", "/data/inbox.db")
    key = required_secret("SIGNING_KEY")
    store.initialize_inbox(path)
    ThreadingHTTPServer(("0.0.0.0", 8080), handler(path, key, name)).serve_forever()


if __name__ == "__main__":
    main()
