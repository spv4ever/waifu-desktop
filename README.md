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

La barra superior separa **Generación de imagen** de **Herramientas de redes**. En
la segunda sección se puede pegar el enlace de una publicación pública de X
(`x.com/.../status/...`), una publicación o Reel de Instagram, una publicación de
TikTok, un vídeo de YouTube o un YouTube Short para descargar
en local sus imágenes o vídeos y guardar
su título, descripción, autor y rutas en SQLite. Los archivos se almacenan por
defecto en `resources/social_media/x`, `resources/social_media/instagram`,
`resources/social_media/tiktok` o `resources/social_media/youtube`; se puede cambiar mediante
`SOCIAL_MEDIA_DIR` en `.env`.

Las publicaciones de X marcadas como contenido sensible requieren una sesión. La
aplicación reintenta automáticamente con las cookies de Chrome, Edge o Firefox si
detecta esos navegadores. Se puede elegir uno explícitamente con
`X_COOKIES_BROWSER=edge` (también `chrome` o `firefox`) en `.env`, o desactivar el
uso de cookies con `X_COOKIES_BROWSER=off`.

La sección **Creador de Shorts** divide un vídeo horizontal 16:9 en el número de
fragmentos indicado. Cada fragmento conserva su tramo de audio y usa un recorte
vertical 9:16 centrado, sin escalar la imagen. Junto a cada MP4 se guardan tres
propuestas de publicación con el nombre de la canción y un enlace configurable al
vídeo completo de YouTube. Es necesario tener `ffmpeg` y `ffprobe` disponibles en
el `PATH`; los resultados se guardan en `outputs/youtube_shorts`.

Importar prompts Dollimages desde JSON:

python -m app.runner.import_dollimages_prompts --path resources/config/dollimages_prompts.example.json

Opcionalmente, puedes usar la variable DOLLIMAGES_PROMPTS_JSON para definir la ruta por defecto y agregar --replace si quieres limpiar los prompts existentes.
