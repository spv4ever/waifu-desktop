from __future__ import annotations

from app.data.storage import MongoStore


def main() -> None:
    store = MongoStore()
    counts = store.sync_from_sqlite()
    print("Sync SQLite -> Mongo completado:")
    for key, value in counts.items():
        print(f" - {key}: {value}")


if __name__ == "__main__":
    main()
