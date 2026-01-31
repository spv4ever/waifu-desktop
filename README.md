git clone https://github.com/tu-usuario/waifu_desktop.git
cd waifu_desktop

python -m venv .venv

.venv\Scripts\activate

(.venv) C:\Python Proyectos\waifu_desktop>

pip install -r requirements.txt

Configuración recomendada (.env):

COMFYUI_BASE_URL=http://127.0.0.1:8188
COMFYUI_DOLLIMAGES_BASE_URL=http://127.0.0.1:8288
COMFYUI_OUTPUT_DIR=output
COMFYUI_INPUT_DIR=input
COMFYUI_CHECKPOINTS_DIR=/ruta/a/ComfyUI/models/checkpoints

Notas:
- COMFYUI_DOLLIMAGES_BASE_URL debe apuntar al nuevo servidor (si aplica).
- COMFYUI_OUTPUT_DIR/COMFYUI_INPUT_DIR deben coincidir con las carpetas de salida/entrada del servidor que uses.
- COMFYUI_CHECKPOINTS_DIR debe apuntar a la carpeta de checkpoints de ComfyUI para que aparezcan en los selectores.

python -m app.runner.init_db
DB inicializada en: resources\data\waifu_desktop.sqlite3

python -m app.runner.run_ui
