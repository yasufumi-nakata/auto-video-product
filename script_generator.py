import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

LM_STUDIO_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1") + "/chat/completions"
API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")

def generate_script(topic_text):
    """
    ニュースや記事のテキストを受け取り、Podcast風の台本（JSON形式）を生成する。
    """
    
    system_prompt = """
    あなたは人気Podcastの構成作家です。
    提供されたニュースやテキストを元に、リスナーが親しみやすく、かつ知的好奇心を刺激されるような「対話形式の台本」を作成してください。
    
    登場人物は2人です：
    1. 「ずんだもん」: 好奇心旺盛で少し生意気なボケ役。語尾は「〜なのだ」「〜のだ」。
    2. 「四国めたん」: 冷静で知的なツッコミ役・解説役。丁寧な口調。

    【重要】出力は必ず以下のJSONフォーマットのみにしてください。
    Markdownのコードブロック(```json)や、冒頭・末尾の挨拶、解説は一切不要です。
    JSONの文法エラー（カンマ漏れ、閉じていない引用符など）がないように注意してください。
    
    Format:
    {
      "title": "エピソードのタイトル",
      "dialogue": [
        {"speaker": "ずんだもん", "text": "ねえねえ、めたん、これ知ってる？"},
        {"speaker": "四国めたん", "text": "あら、また何か見つけたのですか？"}
      ]
    }
    """

    user_prompt = f"以下のテキストを元に、約3分程度の解説トーク台本を作成してください。\n\n【元テキスト】\n{topic_text}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    payload = {
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
