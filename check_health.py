import os
import requests
from dotenv import load_dotenv

load_dotenv()

def check_service(name, url):
    print(f"Checking {name} at {url}...")
    try:
        response = requests.get(url, timeout=5)
        # VOICEVOX returns 404 on root / but it means it's running.
        # ComfyUI returns 200 on root.
        # LM Studio v1/models usually returns 200.
        print(f"  [OK] Status: {response.status_code}")
        return True
    except requests.exceptions.ConnectionError:
        print(f"  [ERROR] Could not connect to {name}. Is it running?")
        return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

def main():
    print("--- System Health Check ---\n")

    # 1. Check LM Studio
    lm_studio_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1") + "/models"
    check_service("LM Studio", lm_studio_url)

    # 2. Check ComfyUI
    comfy_url = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    check_service("ComfyUI", comfy_url)

    # 3. Check VOICEVOX
    # VOICEVOX root endpoint doesn't return 200, check /version instead
    voicevox_url = os.getenv("VOICEVOX_BASE_URL", "http://127.0.0.1:50021") + "/version"
    check_service("VOICEVOX", voicevox_url)

    print("\n---------------------------")

if __name__ == "__main__":
    main()
