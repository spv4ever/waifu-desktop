from app.data.db import init_db
from app.config.settings import settings

def main():
    init_db()
    print(f"DB inicializada en: {settings.db_path}")

if __name__ == "__main__":
    main()
