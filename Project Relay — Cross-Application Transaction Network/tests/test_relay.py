import json
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from relay import api, consumer, store, worker
from relay.http_common import signature
from relay.model import TARGETS, encode, validate

TOKEN = b"operator-test-token-12345678901234567890"
KEYS = {target: (target + "-test-signing-key-" + "x" * 32).encode() for target in TARGETS}


def transaction(identifier="tx-001", quantity=2):
    return {"transaction_id": identifier, "source": "orders", "type": "order.submitted",
            "payload": {"order_id": "ord-001", "sku": "sku-001", "quantity": quantity}}


@contextmanager
def serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def request(url, event=None, headers=None):
    data = encode(event) if event is not None else None
    options = {"Content-Type": "application/json", **(headers or {})}
    try:
        with urlopen(Request(url, data=data, headers=options), timeout=3) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


class RelayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "relay.db"
        store.initialize(self.db)

    def test_model_validation(self):
        self.assertEqual(validate(transaction())["source"], "orders")
        for quantity in [0, -1, 10001, True, "2"]:
            with self.assertRaises(ValueError):
                validate(transaction(quantity=quantity))
        with self.assertRaises(ValueError):
            validate(transaction(identifier="../wrong"))

    def test_atomic_submit_and_conflict(self):
        self.assertEqual(store.submit(self.db, transaction()), "accepted")
        self.assertEqual(store.submit(self.db, transaction()), "duplicate")
        self.assertEqual(store.submit(self.db, transaction(quantity=3)), "conflict")
        stored = store.status(self.db, "tx-001")
        self.assertEqual(len(stored["deliveries"]), 2)
        self.assertEqual({d["status"] for d in stored["deliveries"]}, {"pending"})
        self.assertIsNone(store.status(self.db, "unknown"))

    def test_expired_lease_fences_previous_worker(self):
        store.submit(self.db, transaction())
        first = store.claim(self.db, now=100)
        other = store.claim(self.db, now=100)
        self.assertNotEqual(first["destination"], other["destination"])
        self.assertTrue(store.finish(self.db, other, now=100))
        self.assertIsNone(store.claim(self.db, now=101))
        retry = store.claim(self.db, now=131)
        self.assertEqual(retry["destination"], first["destination"])
        self.assertFalse(store.finish(self.db, first, now=131))
        self.assertTrue(store.finish(self.db, retry, now=131))

    def test_retry_limit_is_durable(self):
        store.submit(self.db, transaction())
        job = store.claim(self.db, now=0)
        other = store.claim(self.db, now=0)
        store.finish(self.db, other, now=0)
        destination = job["destination"]
        for attempt in range(1, store.MAX_ATTEMPTS + 1):
            now = attempt * 100
            self.assertEqual(job["attempts"], attempt)
            store.finish(self.db, job, "unavailable", now=now)
            if attempt < store.MAX_ATTEMPTS:
                self.assertIsNone(store.claim(self.db, now=now+1))
                job = store.claim(self.db, now=now+99)
        self.assertIsNone(store.claim(self.db, now=1000))
        stored = {d["destination"]:d for d in store.status(self.db, "tx-001")["deliveries"]}
        self.assertEqual(stored[destination]["status"], "failed")
        self.assertEqual(stored[destination]["attempts"], store.MAX_ATTEMPTS)

    def test_end_to_end_delivery_and_idempotent_receipts(self):
        inventory = self.root / "inventory.db"
        fulfillment = self.root / "fulfillment.db"
        store.initialize_inbox(inventory)
        store.initialize_inbox(fulfillment)
        headers = {"Authorization": "Bearer " + TOKEN.decode()}
        event = transaction()
        with serve(api.handler(self.db, TOKEN)) as ingress, \
             serve(consumer.handler(inventory, KEYS["inventory"], "inventory")) as a, \
             serve(consumer.handler(fulfillment, KEYS["fulfillment"], "fulfillment")) as b:
            self.assertEqual(request(ingress+"/transactions", event)[0], 401)
            self.assertEqual(request(ingress+"/transactions", event, headers)[0], 202)
            self.assertEqual(request(ingress+"/transactions", event, headers)[1]["status"], "duplicate")
            self.assertEqual(request(ingress+"/transactions", transaction(quantity=3), headers)[0], 409)
            self.assertEqual(request(a+"/inbox", event)[0], 401)
            destinations = {"inventory": a+"/inbox", "fulfillment": b+"/inbox"}
            self.assertTrue(worker.step(self.db, destinations, KEYS))
            self.assertTrue(worker.step(self.db, destinations, KEYS))
            self.assertFalse(worker.step(self.db, destinations, KEYS))
            state, body = request(ingress+"/transactions/tx-001", headers=headers)
            self.assertEqual(state, 200)
            self.assertEqual({d["status"] for d in body["deliveries"]}, {"delivered"})
            self.assertEqual(request(a+"/inbox", event, {"X-Relay-Signature":signature(KEYS["inventory"], encode(event))})[1]["status"], "duplicate")
            self.assertEqual(request(a+"/inbox", transaction(quantity=3), {"X-Relay-Signature":signature(KEYS["inventory"], encode(transaction(quantity=3)))})[0], 409)
        for path in (inventory, fulfillment):
            with store.connection(path) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM inbox").fetchone()[0], 1)

    def test_lost_receipt_is_recovered_by_idempotent_consumer(self):
        inbox = self.root / "inbox.db"
        store.initialize_inbox(inbox)
        store.submit(self.db, transaction())
        now = time.time()
        first = store.claim(self.db, now=now)
        second = store.claim(self.db, now=now)
        target = first["destination"]
        store.finish(self.db, second, now=now)
        with serve(consumer.handler(inbox, KEYS[target], target)) as destination:
            destinations = {target: destination + "/inbox"}
            self.assertIsNone(worker.deliver(first, destinations, KEYS))
            # Simulate the relay worker dying after the receiving app commits.
            retry = store.claim(self.db, now=now+store.LEASE_SECONDS+1)
            self.assertEqual(retry["destination"], target)
            self.assertIsNone(worker.deliver(retry, destinations, KEYS))
            self.assertTrue(store.finish(self.db, retry))
        with store.connection(inbox) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM inbox").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
