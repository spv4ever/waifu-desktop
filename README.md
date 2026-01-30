git clone https://github.com/tu-usuario/waifu_desktop.git
cd waifu_desktop

python -m venv .venv

.venv\Scripts\activate

(.venv) C:\Python Proyectos\waifu_desktop>

pip install -r requirements.txt

python -m app.runner.init_db
DB inicializada en: resources\data\waifu_desktop.sqlite3

python -m app.runner.run_ui

## Backend de datos (SQLite / MongoDB / Dual)

Configura las siguientes variables de entorno en tu `.env`:

```
DATA_BACKEND_MODE=local        # local | mongo | dual
DATA_BACKEND_READ=local        # local | mongo (solo aplica en modo dual)
MONGODB_URI=mongodb://...
MONGODB_DB=waifu_desktop
```

Para migrar los datos actuales de SQLite a MongoDB (local o Atlas):

```
python -m app.runner.sync_mongo_from_sqlite
```

