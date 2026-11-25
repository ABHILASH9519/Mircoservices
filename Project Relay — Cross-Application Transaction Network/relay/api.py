"""Ingress and delivery status service."""
import json
import os
import sqlite3
from http.server import ThreadingHTTPServer

from relay import store
from relay.http_common import Handler, required_secret
from relay.model import IDENTIFIER, validate


def handler(path, token):
    class API(Handler):
        def do_POST(self):
            if self.path != "/transactions":
                return self.reply(404, {"error": "not found"})
            if not self.authorized(token):
                return self.reply(401, {"error": "unauthorized"})
            try:
                event = validate(json.loads(self.body()))
                result = store.submit(path, event)
            except (ValueError, UnicodeError, TypeError):
                return self.reply(400, {"error": "invalid transaction"})
            except sqlite3.Error:
                return self.reply(503, {"error": "store unavailable"})
            identifier = event["transaction_id"]
            if result == "conflict":
                return self.reply(409, {"error": "transaction_id already used with a different body"})
            return self.reply(202 if result == "accepted" else 200,
                              {"transaction_id": identifier, "status": result})

        def do_GET(self):
            if self.path == "/healthz":
                try:
                    with store.connection(path) as db:
                        db.execute("SELECT id FROM events LIMIT 1").fetchone()
                except sqlite3.Error:
                    return self.reply(503, {"status": "unavailable"})
                return self.reply(200, {"status": "ok"})
            identifier = self.path.removeprefix("/transactions/")
            if not self.path.startswith("/transactions/") or not IDENTIFIER.fullmatch(identifier):
                return self.reply(404, {"error": "not found"})
            if not self.authorized(token):
                return self.reply(401, {"error": "unauthorized"})
            try:
                result = store.status(path, identifier)
            except sqlite3.Error:
                return self.reply(503, {"error": "store unavailable"})
            return self.reply(200, result) if result else self.reply(404, {"error": "not found"})

    return API


def main():
    path = os.environ.get("RELAY_DB", "/data/relay.db")
    token = required_secret("RELAY_TOKEN")
    store.initialize(path)
    ThreadingHTTPServer(("0.0.0.0", 8080), handler(path, token)).serve_forever()


if __name__ == "__main__":
    main()
