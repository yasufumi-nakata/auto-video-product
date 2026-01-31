import os
import requests
import json
import re
from dotenv import load_dotenv
from lm_studio_utils import ensure_lm_studio_ready

load_dotenv()

LM_STUDIO_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1") + "/chat/completions"
API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")
DEFAULT_MODEL = "openai/gpt-oss-20b"
DEFAULT_SPEAKER_NAME = os.getenv("VOICEVOX_SPEAKER_NAME", "青山龍星")
CJK_RANGE = r"\u3040-\u30ff\u3400-\u9fff"
SPACE_BETWEEN_CJK = re.compile(rf"(?<=[{CJK_RANGE}0-9])\s+(?=[{CJK_RANGE}0-9])")
SPACE_BETWEEN_CJK_ASCII = re.compile(rf"(?<=[{CJK_RANGE}])\s+(?=[A-Za-z0-9])")
SPACE_BETWEEN_ASCII_CJK = re.compile(rf"(?<=[A-Za-z0-9])\s+(?=[{CJK_RANGE}])")


def resolve_model():
    model = os.getenv("LM_STUDIO_MODEL")
    if model:
        return model

    base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
    try:
        response = requests.get(f"{base_url}/models", timeout=10)
        response.raise_for_status()
        data = response.json().get("data", [])
        for item in data:
            model_id = item.get("id")
            if model_id and "embed" not in model_id.lower():
                return model_id
        if data:
            return data[0].get("id")
    except Exception as e:
        print(f"Warning: Could not fetch LM Studio models: {e}")

    return DEFAULT_MODEL

def normalize_dialogue_text(text):
    if not text:
        return ""
    normalized = re.sub(r"\s+", " ", text).strip()
    normalized = SPACE_BETWEEN_CJK.sub("", normalized)
    normalized = SPACE_BETWEEN_CJK_ASCII.sub("", normalized)
    normalized = SPACE_BETWEEN_ASCII_CJK.sub("", normalized)
    normalized = re.sub(r"\s+([、。！？…])", r"\1", normalized)
    normalized = re.sub(r"([「『（【])\s+", r"\1", normalized)
    normalized = re.sub(r"\s+([」』）】])", r"\1", normalized)
    return normalized

def generate_script(topic_text):
    """
    ニュースや記事のテキストを受け取り、Podcast風の台本（JSON形式）を生成する。
    """
    if not ensure_lm_studio_ready():
        print("LM Studio is not available. Script generation aborted.")
        return None
    
    system_prompt = f"""
    あなたは人気Podcastの構成作家です。
    提供されたニュースやテキストを元に、リスナーが親しみやすく、かつ知的好奇心を刺激されるような「一人語りの台本」を作成してください。
    
    話者は1人です：
    1. 「{DEFAULT_SPEAKER_NAME}」: 落ち着いた丁寧語で話すナレーター。

    【正確性ルール】
    - 元テキストにない情報は推測で断定しない
    - 不明な点は「元テキストからは不明」と明記する

    【敬語の読み上げ】
    - です・ます調で自然に話す
    - スラッシュや括弧で敬語を省略しない

    【読み上げやすさ】
    - 英字略語や英単語は原則カタカナ表記に置き換える（例: AI→エーアイ、Transformer→トランスフォーマー）
    - アルファベット表記が避けられない固有名詞は、本文ではカタカナ読みのみを使う
    - 記号や英単語は必要に応じて読みやすく言い換える

    【表記ルール】
    - 日本語は通常の表記（漢字・ひらがな・カタカナ）で、ひらがなの分かち書きはしない
    - 不要な空白を入れない

    【重要】出力は必ず以下のJSONフォーマットのみにしてください。
    Markdownのコードブロック(```json)や、冒頭・末尾の挨拶、解説は一切不要です。
    JSONの文法エラー（カンマ漏れ、閉じていない引用符など）がないように注意してください。
    
    Format:
    {{
      "title": "エピソードのタイトル",
      "dialogue": [
        {{"speaker": "{DEFAULT_SPEAKER_NAME}", "text": "導入の台詞です。"}},
        {{"speaker": "{DEFAULT_SPEAKER_NAME}", "text": "続けて解説します。"}}
      ]
    }}
    """

    user_prompt = f"""以下のテキストを元に、約5〜6分程度の解説トーク台本を作成してください。

構成指示：
- 導入（話題の全体像）
- 背景や前提の整理（元テキストに基づく範囲）
- 重要ポイントの噛み砕いた言い換え
- 影響や今後の注目点（元テキストにある範囲）
- まとめ

台本は少し長めにし、要点の言い換えや独り言の確認を挟んでください。

【元テキスト】
{topic_text}"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    model = resolve_model()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 2000,
        "stream": False
    }

    print(f"Generating script for topic: {topic_text[:50]}...")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1}/{max_retries}...")
            response = requests.post(LM_STUDIO_URL, headers=headers, json=payload, timeout=600)
            response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # JSON部分だけを抽出する処理
            # Markdownの除去
            content = content.replace("```json", "").replace("```", "").strip()
            
            # 最初の '{' と最後の '}' を探す
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx : end_idx + 1]
            
            script_data = json.loads(content)
            if isinstance(script_data.get("dialogue"), list):
                cleaned_dialogue = []
                for line in script_data["dialogue"]:
                    if not isinstance(line, dict):
                        continue
                    speaker = line.get("speaker") or DEFAULT_SPEAKER_NAME
                    text = normalize_dialogue_text(line.get("text", ""))
                    if text:
                        cleaned_dialogue.append({"speaker": speaker, "text": text})
                script_data["dialogue"] = cleaned_dialogue
            return script_data

        except json.JSONDecodeError:
            print("Error: LM Studio response was not valid JSON.")
            # 最後の試行でなければログを出してリトライ
            if attempt < max_retries - 1:
                print("Retrying...")
            else:
                print("Raw response:", content)
                return None
        except Exception as e:
            print(f"Error communicating with LM Studio: {e}")
            if attempt < max_retries - 1:
                print("Retrying...")
            else:
                return None
    
    return None

if __name__ == "__main__":
    # Test execution
    sample_text = """
    OpenAIは、新しい動画生成AIモデル「Sora」を発表しました。
    テキストのプロンプトから最長1分の高画質動画を生成できます。
    物理法則を理解したようなリアルな動きが特徴ですが、まだ一般公開はされていません。
    """
    
    script = generate_script(sample_text)
    if script:
        print(json.dumps(script, indent=2, ensure_ascii=False))
        
        # Save to file for next step
        with open("script.json", "w", encoding="utf-8") as f:
            json.dump(script, f, indent=2, ensure_ascii=False)
        print("\nScript saved to script.json")
