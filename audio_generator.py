import os
import json
import requests
import time
from dotenv import load_dotenv

load_dotenv()

VOICEVOX_URL = os.getenv("VOICEVOX_BASE_URL", "http://127.0.0.1:50021")

# 話者ID定義
# VOICEVOXアプリのバージョンや設定によりますが、標準的なIDを使用します。
# ずんだもん: 3 (ノーマル), 1 (あまあま)
# 四国めたん: 2 (ノーマル), 0 (あまあま)
SPEAKERS = {
    "ずんだもん": 3,
    "四国めたん": 2
}

def generate_audio_file(text, speaker_name, output_filename):
    """
    VOICEVOX APIを使ってテキストから音声ファイルを生成する。
    1. audio_query を作成
    2. synthesis で音声合成
    """
    speaker_id = SPEAKERS.get(speaker_name, 3) # デフォルトはずんだもん
    
    # 1. Query Creation
    query_payload = {"text": text, "speaker": speaker_id}
    try:
        query_res = requests.post(f"{VOICEVOX_URL}/audio_query", params=query_payload, timeout=10)
        query_res.raise_for_status()
        query_data = query_res.json()
    except Exception as e:
        print(f"Error creating audio query for {speaker_name}: {e}")
        return False

    # 2. Synthesis
    try:
        synth_res = requests.post(
            f"{VOICEVOX_URL}/synthesis",
            headers={"Content-Type": "application/json"},
            params={"speaker": speaker_id},
            json=query_data,
            timeout=60
        )
        synth_res.raise_for_status()
        
        with open(output_filename, "wb") as f:
            f.write(synth_res.content)
        
        return True
    except Exception as e:
        print(f"Error synthesizing audio for {speaker_name}: {e}")
        return False

def process_script(script_file="script.json", output_dir="output_audio"):
    """
    script.json を読み込み、全てのセリフを音声化して保存する。
    """
    if not os.path.exists(script_file):
        print(f"Script file {script_file} not found.")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(script_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    dialogues = data.get("dialogue", [])
    print(f"Processing {len(dialogues)} lines of dialogue...")

    audio_files = []

    for i, line in enumerate(dialogues):
        speaker = line["speaker"]
        text = line["text"]
        filename = os.path.join(output_dir, f"{i:03d}_{speaker}.wav")
        
        print(f"[{i+1}/{len(dialogues)}] Generating {speaker}: {text[:20]}...")
        success = generate_audio_file(text, speaker, filename)
        
        if success:
            audio_files.append(filename)
        else:
            print("  -> Failed.")
        
        # 少し待機（API負荷軽減）
        time.sleep(0.1)

    print("\nAudio generation complete!")
    return audio_files

if __name__ == "__main__":
    # Test execution
    # 事前に script_generator.py で作成された script.json を使用
    process_script()
