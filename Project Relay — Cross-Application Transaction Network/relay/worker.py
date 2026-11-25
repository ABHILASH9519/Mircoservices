"""Deliver durable events to configured applications with bounded retries."""
import json
import os
import sqlite3
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener, ProxyHandler

from relay import store
from relay.http_common import required_secret, signature
from relay.model import TARGETS


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def deliver(job, destinations, keys):
    target = job["destination"]
    raw = job["body"]
    request = Request(destinations[target], data=raw, headers={
        "Content-Type": "application/json",
        "X-Relay-Signature": signature(keys[target], raw),
    })
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=5) as response:
            if response.status != 200:
                return f"HTTP {response.status}"
            body = response.read(4097)
            if len(body) > 4096:
                return "invalid receipt"
            receipt = json.loads(body)
            if not isinstance(receipt, dict) or (
                receipt.get("transaction_id") != job["id"] or
                receipt.get("application") != target or
                receipt.get("status") not in ("accepted", "duplicate")
            ):
                return "invalid receipt"
        return None
    except HTTPError as error:
        return f"HTTP {error.code}"
    except (URLError, TimeoutError, OSError, ValueError, HTTPException):
        return "delivery unavailable"


def step(path, destinations, keys):
    job = store.claim(path)
    if job is None:
        return False
    error = deliver(job, destinations, keys)
    store.finish(path, job, error)
    return True


def main():
    path = os.environ.get("RELAY_DB", "/data/relay.db")
    destinations = {target: f"http://{target}:8080/inbox" for target in TARGETS}
    keys = {target: required_secret(target.upper() + "_SIGNING_KEY") for target in TARGETS}
    store.initialize(path)
    while True:
        try:
            if not step(path, destinations, keys):
                time.sleep(1)
        except sqlite3.Error:
            time.sleep(2)


if __name__ == "__main__":
    main()
