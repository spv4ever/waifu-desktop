from app.config.settings import settings

def main():
    print("ComfyUI URL:", settings.comfyui_base_url)
    print("ComfyUI Dollimages URL:", settings.comfyui_dollimages_base_url or "(usa COMFYUI_BASE_URL)")
    print("Poll interval:", settings.comfyui_poll_interval)
    print("Timeout:", settings.comfyui_request_timeout)
    print("Max in flight:", settings.queue_max_in_flight)

if __name__ == "__main__":
    main()
