import websocket
import uuid
import json
import urllib.request
import urllib.parse
import os
import time
from dotenv import load_dotenv

load_dotenv()

SERVER_ADDRESS = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188").replace("http://", "")
CLIENT_ID = str(uuid.uuid4())

def queue_prompt(prompt):
    p = {"prompt": prompt, "client_id": CLIENT_ID}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(f"http://{SERVER_ADDRESS}/prompt", data=data)
    return json.loads(urllib.request.urlopen(req).read())

def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen(f"http://{SERVER_ADDRESS}/view?{url_values}") as response:
        return response.read()

def get_history(prompt_id):
    with urllib.request.urlopen(f"http://{SERVER_ADDRESS}/history/{prompt_id}") as response:
        return json.loads(response.read())

def generate_image(prompt_text, output_path="thumbnail.png"):
    """
    ComfyUI APIを使用して画像を生成し、指定したパスに保存する。
    """
    # 基本的なText to Imageワークフロー
    # 注意: モデル名はダウンロードしたものと一致させる必要があります
    MODEL_NAME = "v1-5-pruned-emaonly.safetensors" 
    
    prompt_workflow = {
        "3": {
            "inputs": {
                "seed": int(time.time()), # ランダムシード
                "steps": 20,
                "cfg": 8,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler"
        },
        "4": {
            "inputs": {
                "ckpt_name": MODEL_NAME
            },
            "class_type": "CheckpointLoaderSimple"
        },
        "5": {
            "inputs": {
                "width": 512, # 正方形 (サムネ用に必要なら変更)
                "height": 512,
                "batch_size": 1
            },
            "class_type": "EmptyLatentImage"
        },
        "6": {
            "inputs": {
                "text": f"masterpiece, best quality, anime style, {prompt_text}", # プロンプト
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "7": {
            "inputs": {
                "text": "low quality, bad anatomy, text, watermark", # ネガティブプロンプト
                "clip": ["4", 1]
            },
            "class_type": "CLIPTextEncode"
        },
        "8": {
            "inputs": {
                "samples": ["3", 0],
                "vae": ["4", 2]
            },
            "class_type": "VAEDecode"
        },
        "9": {
            "inputs": {
                "filename_prefix": "ComfyUI_API_Result",
                "images": ["8", 0]
            },
            "class_type": "SaveImage"
        }
    }

    try:
        ws = websocket.WebSocket()
        ws.connect(f"ws://{SERVER_ADDRESS}/ws?clientId={CLIENT_ID}")
        
        print(f"Queueing prompt: {prompt_text}...")
        prompt_id = queue_prompt(prompt_workflow)['prompt_id']
        
        # 完了待ち
        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message['type'] == 'executing':
                    data = message['data']
                    if data['node'] is None and data['prompt_id'] == prompt_id:
                        break # 生成完了
        
        # 履歴からファイル名を取得してダウンロード
        history = get_history(prompt_id)[prompt_id]
        for node_id in history['outputs']:
            node_output = history['outputs'][node_id]
            if 'images' in node_output:
                for image in node_output['images']:
                    image_data = get_image(image['filename'], image['subfolder'], image['type'])
                    
                    with open(output_path, 'wb') as f:
                        f.write(image_data)
                    print(f"Image saved to {output_path}")
                    return output_path

    except Exception as e:
        print(f"Error generating image: {e}")
        return None

if __name__ == "__main__":
    # Test execution
    generate_image("A futuristic city with flying cars, blue sky", "test_thumbnail.png")
