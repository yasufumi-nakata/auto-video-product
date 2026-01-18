import torch
from diffusers import StableDiffusionPipeline
import os

def generate_thumbnail(prompt, output_filename="thumbnail.png"):
    print(f"Generating thumbnail for: {prompt}")
    
    # M1 Mac (Apple Silicon) 用の設定
    # "mps" デバイスを使用することでGPU加速が可能
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using device: {device}")

    try:
        # モデルのロード (初回はダウンロードが走ります)
        # runwayml/stable-diffusion-v1-5 は標準的で安定しています
        model_id = "runwayml/stable-diffusion-v1-5"
        
        pipe = StableDiffusionPipeline.from_pretrained(
            model_id, 
            torch_dtype=torch.float16, 
            use_safetensors=True,
            safety_checker=None  # フィルター無効化
        )
        pipe = pipe.to(device)
        
        # Apple Silicon向けの推奨設定 (Attention Slicing)
        pipe.enable_attention_slicing()

        # 生成実行
        image = pipe(
            prompt, 
            height=512, 
            width=512, 
            num_inference_steps=30
        ).images[0]

        # 保存
        image.save(output_filename)
        print(f"Successfully saved to {output_filename}")
        return output_filename

    except Exception as e:
        print(f"Error generating image: {e}")
        return None

if __name__ == "__main__":
    # Test execution
    prompt_text = "masterpiece, best quality, a radio studio with a cute green haired anime girl and a pink haired elegant anime girl talking, microphone, on air sign, highly detailed, 4k"
    generate_thumbnail(prompt_text)
