import os
import requests
import json
import re
from dotenv import load_dotenv
from lm_studio_utils import ensure_lm_studio_ready

load_dotenv()

LM_STUDIO_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1") + "/chat/completions"
API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")
DEFAULT_MODEL = "openai/gpt-oss-20b" # Will be resolved dynamically
DEFAULT_SPEAKER_NAME = os.getenv("VOICEVOX_SPEAKER_NAME", "青山龍星")

def resolve_model():
    model = os.getenv("LM_STUDIO_MODEL")
    if model:
        return model
    # Fallback resolution same as script_generator.py
    base_url = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
    try:
        response = requests.get(f"{base_url}/models", timeout=5)
        if response.status_code == 200:
            data = response.json().get("data", [])
            if data: return data[0].get("id")
    except:
        pass
    return DEFAULT_MODEL

def normalize_dialogue_text(text):
    # Same normalization as script_generator.py
    if not text: return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text

def chunk_text(text, max_chars=2000):
    """
    Splits text into chunks of roughly max_chars, respecting newlines/headers if possible.
    """
    if len(text) <= max_chars:
        return [text]
        
    chunks = []
    current_chunk = ""
    
    # Split by double newlines to preserve paragraphs
    paragraphs = text.split("\n\n")
    
    for para in paragraphs:
        if len(current_chunk) + len(para) < max_chars:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = para + "\n\n"
            
            # If a single paragraph is huge (unlikely but possible), split it blindly
            while len(current_chunk) > max_chars:
                chunks.append(current_chunk[:max_chars])
                current_chunk = current_chunk[max_chars:]
                
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks

def generate_section_script(title, section_text, section_type="middle", model=None):
    """
    Generates a script fragment for a specific section.
    section_type: "intro", "middle", "outro"
    """
    
    system_prompt = f"""
    あなたは科学解説Podcastの構成作家です。
    脳科学辞典の項目「{title}」について、ナレーター「{DEFAULT_SPEAKER_NAME}」が解説する台本の一部を作成してください。
    
    【役割】
    section_type="{section_type}"
    
    - "intro": 番組の開始。タイトルの紹介、導入、なぜこれが重要か。
    - "middle": 話題の続き。詳細な解説。
    - "outro": 最後のまとめ。今後の展望、番組の締めくくり。

    【制約】
    - 出力はJSON形式のみ。
    - 専門用語は噛み砕くか、難解な場合は補足を入れる。
    - 英語略語はカタカナ読み（例: DNA→ディーエヌエー）。
    
    Format:
    {{
      "dialogue": [
        {{"speaker": "{DEFAULT_SPEAKER_NAME}", "text": "..."}}
      ]
    }}
    """
    
    user_prompt = f"""
    以下のテキストを元に、台本のパートを作成してください。
    
    【元テキスト】
    {section_text}
    """
    
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
    
    try:
        response = requests.post(LM_STUDIO_URL, headers={"Content-Type": "application/json"}, json=payload, timeout=600)
        response.raise_for_status()
        
        content = response.json()['choices'][0]['message']['content']
        # Extract JSON
        content = content.replace("```json", "").replace("```", "").strip()
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1:
            content = content[start:end+1]
            
        data = json.loads(content)
        return data.get("dialogue", [])
    except Exception as e:
        print(f"Error generating section ({section_type}): {e}")
        return []

def generate_bsd_script(article_data):
    """
    Main function to generate full script from BSD article data.
    """
    if not ensure_lm_studio_ready():
        print("LM Studio is not available. Script generation aborted.")
        return None
    title = article_data['title']
    content = article_data['content']
    
    print(f"Generating script for: {title} (Length: {len(content)})")
    
    chunks = chunk_text(content, max_chars=1500) # Conservative limit
    full_dialogue = []
    
    model = resolve_model()
    
    for i, chunk in enumerate(chunks):
        section_type = "middle"
        if i == 0:
            section_type = "intro"
        elif i == len(chunks) - 1:
            section_type = "outro"
            
        print(f"Processing chunk {i+1}/{len(chunks)} ({section_type})...")
        dialogue_part = generate_section_script(title, chunk, section_type, model)
        
        # Add normalization
        for line in dialogue_part:
            line['text'] = normalize_dialogue_text(line['text'])
            
        full_dialogue.extend(dialogue_part)
        
    return {
        "title": title,
        "dialogue": full_dialogue,
        "source_url": article_data['url']
    }

if __name__ == "__main__":
    # Test with dummy data
    dummy_data = {
        "title": "テスト記事",
        "content": "これはテストです。" * 100,
        "url": "http://example.com"
    }
    script = generate_bsd_script(dummy_data)
    print(json.dumps(script, indent=2, ensure_ascii=False))
