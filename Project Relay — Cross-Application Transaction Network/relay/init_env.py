"""Generate local credentials once in the project directory."""
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]


def main():
    path = root / ".env"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print("Existing .env retained.")
        return
    with os.fdopen(fd, "w") as file:
        for name in ("RELAY_TOKEN", "INVENTORY_SIGNING_KEY", "FULFILLMENT_SIGNING_KEY"):
            file.write(f"{name}={secrets.token_hex(32)}\n")
    print("Created private .env.")


if __name__ == "__main__":
    main()
