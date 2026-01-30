from __future__ import annotations

from app.domain.models import PackCreate
from app.services.pack_service import PackService


def main():
    service = PackService()

    req = PackCreate(
        category="casual",
        variant="v01",
        requested_n=2,
        notes="demo inicial",
    )

    result = service.create_pack_and_enqueue(None, req)
    print("Pack creado:", result.pack_id)
    print("Prompt items:", len(result.created_prompt_item_ids))
    print("Queue jobs:", len(result.created_queue_job_ids))


if __name__ == "__main__":
    main()
