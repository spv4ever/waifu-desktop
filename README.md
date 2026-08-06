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
COMFYUI_IMAGE2VID_OUTPUT_DIR=C:\\StabilyMatrix\\Data\\Packages\\ComfyUI-dev\\output
COMFYUI_INPUT_DIR=input
COMFYUI_CHECKPOINTS_DIR=/ruta/a/ComfyUI/models/checkpoints

Notas:
- COMFYUI_DOLLIMAGES_BASE_URL debe apuntar al nuevo servidor (si aplica).
- COMFYUI_OUTPUT_DIR/COMFYUI_INPUT_DIR deben coincidir con las carpetas de salida/entrada del servidor que uses.
- COMFYUI_IMAGE2VID_OUTPUT_DIR permite definir una salida específica para videos Image2Vid (por ejemplo `C:\\StabilyMatrix\\Data\\Packages\\ComfyUI-dev\\output`).
- COMFYUI_CHECKPOINTS_DIR debe apuntar a la carpeta de checkpoints de ComfyUI para que aparezcan en los selectores.

python -m app.runner.init_db
DB inicializada en: resources\data\waifu_desktop.sqlite3

python -m app.runner.run_ui

Importar prompts Dollimages desde JSON:

python -m app.runner.import_dollimages_prompts --path resources/config/dollimages_prompts.example.json

Opcionalmente, puedes usar la variable DOLLIMAGES_PROMPTS_JSON para definir la ruta por defecto y agregar --replace si quieres limpiar los prompts existentes.

Bibliotecas temáticas para Bulk Images:

- `resources/config/bulk_images_prompts/summer.json`
- `resources/config/bulk_images_prompts/bikinis.json`
- `resources/config/bulk_images_prompts/snow.json`
- `resources/config/bulk_images_prompts/saunas.json`
- `resources/config/bulk_images_prompts/iconic_travel.json`

Cada archivo se puede importar por separado desde **Bulk Images → Importar prompts desde JSON**. Los identificadores son únicos entre bibliotecas, así que también se pueden importar todas para combinarlas en la biblioteca local.
