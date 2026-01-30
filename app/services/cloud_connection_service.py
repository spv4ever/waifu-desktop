from __future__ import annotations

from dataclasses import dataclass

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.config.settings import settings


@dataclass(frozen=True)
class CloudConnectionResult:
    ok: bool
    message: str


def check_mongodb_connection() -> CloudConnectionResult:
    if not settings.mongodb_uri:
        return CloudConnectionResult(
            False,
            "MONGODB_URI no está configurada en el archivo .env.",
        )

    client: MongoClient | None = None
    try:
        client = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
        )
        client.admin.command("ping")
        if settings.mongodb_db:
            client[settings.mongodb_db].list_collection_names()
        return CloudConnectionResult(True, "Conexión a MongoDB verificada.")
    except PyMongoError as exc:
        return CloudConnectionResult(
            False,
            f"No se pudo conectar a MongoDB: {exc}",
        )
    finally:
        if client is not None:
            try:
                client.close()
            except PyMongoError:
                pass
