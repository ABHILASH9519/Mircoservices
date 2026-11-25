import json
import re

TARGETS = ("inventory", "fulfillment")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def validate(event):
    if not isinstance(event, dict) or set(event) != {"transaction_id", "source", "type", "payload"}:
        raise ValueError("Expected transaction_id, source, type and payload")
    identifier = event["transaction_id"]
    if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
        raise ValueError("Invalid transaction_id")
    if event["source"] != "orders" or event["type"] != "order.submitted":
        raise ValueError("Supported source/type: orders / order.submitted")
    payload = event["payload"]
    if not isinstance(payload, dict) or set(payload) != {"order_id", "sku", "quantity"}:
        raise ValueError("Expected payload with order_id, sku and quantity")
    for name in ("order_id", "sku"):
        value = payload[name]
        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
            raise ValueError(f"Invalid {name}")
    if type(payload["quantity"]) is not int or not 1 <= payload["quantity"] <= 10000:
        raise ValueError("Quantity must be an integer between 1 and 10000")
    return event
