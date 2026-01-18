from huggingface_hub import hf_hub_download
import shutil
import os

repo_id = "runwayml/stable-diffusion-v1-5"
filename = "v1-5-pruned-emaonly.safetensors"
target_dir = "ComfyUI/models/checkpoints"

print(f"Downloading {filename} from {repo_id}...")

try:
    # ダウンロード（キャッシュされます）
    cached_path = hf_hub_download(repo_id=repo_id, filename=filename)
    
    # ComfyUIのフォルダへコピー
    target_path = os.path.join(target_dir, filename)
    shutil.copy(cached_path, target_path)
    
    print(f"Successfully downloaded to {target_path}")

except Exception as e:
    print(f"Error downloading model: {e}")
