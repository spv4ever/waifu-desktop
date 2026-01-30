from __future__ import annotations

from app.data.storage import get_store


def main():
    store = get_store()
    paused = store.kv_get("queue_paused", "false")
    print("queue_paused =", paused)


if __name__ == "__main__":
    main()
