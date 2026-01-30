from __future__ import annotations

from app.data.storage import get_store


def main():
    store = get_store()
    store.kv_set("queue_paused", "true")
    print("OK: cola pausada")


if __name__ == "__main__":
    main()
