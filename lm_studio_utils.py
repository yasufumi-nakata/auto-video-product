import os
import time
import subprocess
import platform
import requests

LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_HEALTH_URL = f"{LM_STUDIO_BASE_URL}/models"
LM_STUDIO_AUTO_START = os.getenv("LM_STUDIO_AUTO_START", "1") != "0"
LM_STUDIO_STARTUP_TIMEOUT = float(os.getenv("LM_STUDIO_STARTUP_TIMEOUT", "30"))
LM_STUDIO_STARTUP_POLL = float(os.getenv("LM_STUDIO_STARTUP_POLL", "0.5"))
LM_STUDIO_APP_NAME = os.getenv("LM_STUDIO_APP_NAME", "LM Studio")

LM_STUDIO_READY_CACHE = None


def lm_studio_is_ready():
    try:
        res = requests.get(LM_STUDIO_HEALTH_URL, timeout=2)
        return res.status_code == 200
    except Exception:
        return False


def attempt_start_lm_studio():
    if not LM_STUDIO_AUTO_START:
        return False
    if platform.system() == "Darwin":
        try:
            subprocess.run(
                ["open", "-a", LM_STUDIO_APP_NAME],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False
    return False


def ensure_lm_studio_ready():
    global LM_STUDIO_READY_CACHE
    if LM_STUDIO_READY_CACHE:
        return True
    if lm_studio_is_ready():
        LM_STUDIO_READY_CACHE = True
        return True
    if not LM_STUDIO_AUTO_START:
        print("LM Studio is not reachable and auto-start is disabled.")
        return False
    if attempt_start_lm_studio():
        print("LM Studio is not running. Attempting to launch LM Studio...")
        deadline = time.time() + LM_STUDIO_STARTUP_TIMEOUT
        while time.time() < deadline:
            if lm_studio_is_ready():
                LM_STUDIO_READY_CACHE = True
                print("LM Studio server is now available.")
                return True
            time.sleep(LM_STUDIO_STARTUP_POLL)
        print("LM Studio did not start within the timeout.")
        return False
    print("LM Studio is not reachable and could not be started automatically.")
    return False
