git clone https://github.com/tu-usuario/waifu_desktop.git
cd waifu_desktop

python -m venv .venv

.venv\Scripts\activate

(.venv) C:\Python Proyectos\waifu_desktop>

pip install -r requirements.txt

python -m app.runner.init_db
DB inicializada en: resources\data\waifu_desktop.sqlite3

python -m app.runner.run_ui
