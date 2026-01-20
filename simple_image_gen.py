import torch
from diffusers import StableDiffusionPipeline
import os
import numpy as np

def generate_thumbnail(prompt, output_filename="thumbnail.png"):
    print(f"Generating thumbnail for: {prompt}")

    # M1 Mac (Apple Silicon) 用の設定
    # MPS + float16でNaN問題が発生するため、float32を使用
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using device: {device}")

    try:
        # モデルのロード (初回はダウンロードが走ります)
        model_id = "runwayml/stable-diffusion-v1-5"

        # MPSではfloat32を使用（float16だとNaNが発生し黒画像になる）
        dtype = torch.float32 if device == "mps" else torch.float16
        print(f"Using dtype: {dtype}")

        pipe = StableDiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=dtype,
            use_safetensors=True,
            safety_checker=None  # フィルター無効化
        )
        pipe = pipe.to(device)

        # Apple Silicon向けの推奨設定 (Attention Slicing)
        pipe.enable_attention_slicing()

        # 生成実行
        result = pipe(
            prompt,
            height=512,
            width=512,
            num_inference_steps=30
        )
        image = result.images[0]

        # 画像が正常か確認（真っ黒チェック）
        img_array = np.array(image)
        if img_array.max() == 0:
            print("Warning: Generated image is completely black, retrying with CPU...")
            # CPUでリトライ
            pipe = pipe.to("cpu")
            result = pipe(
                prompt,
                height=512,
                width=512,
                num_inference_steps=30
            )
            image = result.images[0]

        # 保存
        image.save(output_filename)
        print(f"Successfully saved to {output_filename}")
        return output_filename

    except Exception as e:
        print(f"Error generating image: {e}")
        # CPUフォールバック
        try:
            print("Attempting CPU fallback...")
            pipe = StableDiffusionPipeline.from_pretrained(
                "runwayml/stable-diffusion-v1-5",
                torch_dtype=torch.float32,
                use_safetensors=True,
                safety_checker=None
            )
            pipe = pipe.to("cpu")
            pipe.enable_attention_slicing()

            result = pipe(
                prompt,
                height=512,
                width=512,
                num_inference_steps=30
            )
            image = result.images[0]
            image.save(output_filename)
            print(f"Successfully saved to {output_filename} (CPU fallback)")
            return output_filename
        except Exception as fallback_e:
            print(f"CPU fallback also failed: {fallback_e}")
            return None

if __name__ == "__main__":
    # Test execution
    prompt_text = "masterpiece, best quality, a radio studio with a cute green haired anime girl and a pink haired elegant anime girl talking, microphone, on air sign, highly detailed, 4k"
    generate_thumbnail(prompt_text)
