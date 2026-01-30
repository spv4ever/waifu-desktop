from __future__ import annotations

from app.data.storage import get_store


def main():
    store = get_store()
    rows = store.fetch_queue_status_counts()

    print("Estado cola (queue_job):")
    if not rows:
        print("  (vacía)")
    for status, count in rows.items():
        print(f" - {status}: {count}")

    rows2 = store.fetch_prompt_status_counts()

    print("\nEstado prompts (prompt_item):")
    if not rows2:
        print("  (vacío)")
    for status, count in rows2.items():
        if status == "TOTAL":
            continue
        print(f" - {status}: {count}")


if __name__ == "__main__":
    main()
