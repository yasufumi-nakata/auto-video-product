import os
import numpy as np

try:
    import torch
except Exception:
    torch = None

def _safe_ascii(text, max_len=80):
    cleaned = "".join(ch if 32 <= ord(ch) < 127 else " " for ch in text or "")
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3].rstrip() + "..."
    return cleaned


def _load_font(size):
    try:
        from PIL import ImageFont
    except Exception:
        return None

    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _generate_placeholder_thumbnail(prompt, output_filename):
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        print(f"Placeholder thumbnail failed (PIL missing): {exc}")
        return None

    width, height = 1280, 720
    base = Image.new("RGB", (width, height), (18, 24, 32))
    draw = ImageDraw.Draw(base)

    for y in range(height):
        shade = int(22 + (y / height) * 60)
        draw.line([(0, y), (width, y)], fill=(shade, shade + 18, shade + 35))

    draw.ellipse((width - 360, -120, width + 80, 320), fill=(255, 166, 90))
    draw.rectangle((0, height - 160, width, height), fill=(12, 16, 22))

    title_font = _load_font(64)
    subtitle_font = _load_font(32)
    title_text = "Brain Tech News"
    subtitle_text = _safe_ascii(prompt)

    title_color = (245, 246, 248)
    subtitle_color = (210, 225, 240)

    if title_font:
        draw.text((70, 90), title_text, font=title_font, fill=title_color)
    if subtitle_font and subtitle_text:
        draw.text((70, 170), subtitle_text, font=subtitle_font, fill=subtitle_color)

    base.save(output_filename)
    print(f"Saved placeholder thumbnail to {output_filename}")
    return output_filename


def generate_thumbnail(prompt, output_filename="thumbnail.png"):
    print(f"Generating thumbnail for: {prompt}")

    if os.getenv("SKIP_DIFFUSERS") == "1":
        print("SKIP_DIFFUSERS=1 detected. Using placeholder thumbnail.")
        return _generate_placeholder_thumbnail(prompt, output_filename)

    if torch is None:
        print("Torch is not available. Using placeholder thumbnail.")
        return _generate_placeholder_thumbnail(prompt, output_filename)

    # M1 Mac (Apple Silicon) 用の設定
    # MPS + float16でNaN問題が発生するため、float32を使用
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Using device: {device}")

    try:
        from diffusers import StableDiffusionPipeline

        # モデルのロード (初回はダウンロードが走ります)
        model_id = "runwayml/stable-diffusion-v1-5"

        # MPSではfloat32を使用（float16だとNaNが発生し黒画像になる）
        dtype = torch.float16 if device == "cuda" else torch.float32
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
        return _generate_placeholder_thumbnail(prompt, output_filename)

if __name__ == "__main__":
    # Test execution
    prompt_text = "masterpiece, best quality, a radio studio with a cute green haired anime girl and a pink haired elegant anime girl talking, microphone, on air sign, highly detailed, 4k"
    generate_thumbnail(prompt_text)
