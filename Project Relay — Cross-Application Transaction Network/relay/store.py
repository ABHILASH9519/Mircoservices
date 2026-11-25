import sqlite3
import time
import uuid
from contextlib import contextmanager

from relay.model import TARGETS, encode

MAX_ATTEMPTS = 6
LEASE_SECONDS = 30


@contextmanager
def connection(path):
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(path):
    with connection(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, body BLOB NOT NULL, created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                id TEXT NOT NULL REFERENCES events(id), destination TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0,
                leased_until REAL NOT NULL DEFAULT 0, lease TEXT, last_error TEXT,
                PRIMARY KEY (id, destination)
            );
            CREATE INDEX IF NOT EXISTS pending_delivery
                ON deliveries(status, next_at, leased_until);
        """)


def submit(path, event):
    """Persist the transaction and both outgoing deliveries atomically."""
    body = encode(event)
    identifier = event["transaction_id"]
    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT body FROM events WHERE id=?", (identifier,)).fetchone()
        if existing:
            if existing["body"] != body:
                return "conflict"
            return "duplicate"
        db.execute("INSERT INTO events VALUES (?, ?, ?)", (identifier, body, time.time()))
        db.executemany("INSERT INTO deliveries(id,destination) VALUES (?,?)",
                       [(identifier, target) for target in TARGETS])
        return "accepted"


def status(path, identifier):
    with connection(path) as db:
        event = db.execute("SELECT created_at FROM events WHERE id=?", (identifier,)).fetchone()
        if event is None:
            return None
        rows = db.execute("""
            SELECT destination,status,attempts,last_error FROM deliveries
            WHERE id=? ORDER BY destination
        """, (identifier,)).fetchall()
        return {"transaction_id": identifier, "created_at": event["created_at"],
                "deliveries": [dict(row) for row in rows]}


def claim(path, now=None):
    now = time.time() if now is None else now
    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        # A process may have died during its last allowed attempt.
        db.execute("""
            UPDATE deliveries SET status='failed', lease=NULL,
                last_error='attempt limit reached after lease expiry'
            WHERE status='delivering' AND leased_until<=? AND attempts>=?
        """, (now, MAX_ATTEMPTS))
        row = db.execute("""
            SELECT d.id, d.destination, d.attempts, e.body FROM deliveries d
            JOIN events e ON e.id=d.id
            WHERE d.attempts<? AND
                ((d.status='pending' AND d.next_at<=?) OR
                 (d.status='delivering' AND d.leased_until<=?))
            ORDER BY d.next_at, d.id, d.destination LIMIT 1
        """, (MAX_ATTEMPTS, now, now)).fetchone()
        if row is None:
            return None
        lease = str(uuid.uuid4())
        db.execute("""
            UPDATE deliveries SET status='delivering', attempts=attempts+1,
                lease=?, leased_until=? WHERE id=? AND destination=?
        """, (lease, now + LEASE_SECONDS, row["id"], row["destination"]))
        return {**dict(row), "attempts": row["attempts"] + 1, "lease": lease}


def finish(path, job, error=None, now=None):
    now = time.time() if now is None else now
    if error is None:
        state = "delivered"
    elif job["attempts"] >= MAX_ATTEMPTS:
        state = "failed"
    else:
        state = "pending"
    delay = min(60, 2 ** job["attempts"])
    with connection(path) as db:
        result = db.execute("""
            UPDATE deliveries SET status=?, next_at=?, lease=NULL, last_error=?
            WHERE id=? AND destination=? AND status='delivering' AND lease=?
        """, (state, now + delay, error, job["id"], job["destination"], job["lease"]))
        return result.rowcount == 1


def initialize_inbox(path):
    with connection(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("""
            CREATE TABLE IF NOT EXISTS inbox (
                id TEXT PRIMARY KEY, body BLOB NOT NULL, received_at REAL NOT NULL
            )
        """)


def receive(path, event):
    """The application's receipt ledger is its own durable datastore."""
    body = encode(event)
    identifier = event["transaction_id"]
    with connection(path) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT body FROM inbox WHERE id=?", (identifier,)).fetchone()
        if existing:
            return "duplicate" if existing["body"] == body else "conflict"
        db.execute("INSERT INTO inbox VALUES (?, ?, ?)", (identifier, body, time.time()))
        return "accepted"
