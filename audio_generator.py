import os
import json
import requests
import time
import re
from dotenv import load_dotenv

load_dotenv()

VOICEVOX_URL = os.getenv("VOICEVOX_BASE_URL", "http://127.0.0.1:50021")
DEFAULT_SPEAKER_NAME = os.getenv("VOICEVOX_SPEAKER_NAME", "青山龍星")
try:
    DEFAULT_SPEAKER_ID = int(os.getenv("VOICEVOX_SPEAKER_ID", "3"))
except ValueError:
    DEFAULT_SPEAKER_ID = 3

# 話者ID定義
# VOICEVOXアプリのバージョンや設定によりますが、標準的なIDを使用します。
# ずんだもん: 3 (ノーマル), 1 (あまあま)
# 四国めたん: 2 (ノーマル), 0 (あまあま)
SPEAKERS = {
    "ずんだもん": 3,
    "四国めたん": 2
}

# ファイル名用の英語マッピング (日本語ファイル名を回避)
SPEAKER_EN_MAP = {
    "ずんだもん": "zundamon",
    "四国めたん": "metan",
    "青山龍星": "aoyama_ryusei"
}

ABBREVIATION_READINGS = [
    ("fMRI", "エフエムアールアイ"),
    ("sEEG", "エスイーイージー"),
    ("iEEG", "アイイーイージー"),
    ("EEG", "イーイージー"),
    ("MEG", "エムイージー"),
    ("EMG", "イーエムジー"),
    ("ECG", "イーシージー"),
    ("ERP", "イーアールピー"),
    ("MRI", "エムアールアイ"),
    ("PET", "ピーイーティー"),
    ("BCI", "ビーシーアイ"),
    ("CNN", "シーエヌエヌ"),
    ("RNN", "アールエヌエヌ"),
    ("GRU", "ジーアールユー"),
    ("LSTM", "エルエスティーエム"),
    ("SVM", "エスブイエム"),
    ("AI", "エーアイ"),
    ("ML", "エムエル"),
    ("DL", "ディーエル"),
    ("AR", "エーアール"),
    ("VR", "ブイアール"),
]

ABBREVIATION_PATTERNS = [
    (re.compile(rf"(?<![A-Za-z0-9]){re.escape(abbr)}(?![A-Za-z0-9])"), reading)
    for abbr, reading in ABBREVIATION_READINGS
]

HONORIFIC_SPLIT_PATTERN = re.compile(
    r"(です|ます|ございます|いたします|ください|下さい)[/／・](です|ます|ございます|いたします|ください|下さい)"
)

SPEAKER_ID_CACHE = None

def normalize_tts_text(text):
    normalized = text
    normalized = HONORIFIC_SPLIT_PATTERN.sub(r"\1、\2", normalized)
    for pattern, reading in ABBREVIATION_PATTERNS:
        normalized = pattern.sub(reading, normalized)
    normalized = normalized.replace("/", "スラッシュ")
    normalized = normalized.replace("／", "スラッシュ")
    return normalized

def pick_default_style_id(styles):
    for style in styles:
        if style.get("name") == "ノーマル":
            return style.get("id")
    if styles:
        return styles[0].get("id")
    return None

def load_voicevox_speakers():
    global SPEAKER_ID_CACHE
    if SPEAKER_ID_CACHE is not None:
        return SPEAKER_ID_CACHE

    speaker_map = {}
    try:
        res = requests.get(f"{VOICEVOX_URL}/speakers", timeout=10)
        res.raise_for_status()
        data = res.json()
        for speaker in data:
            name = speaker.get("name")
            styles = speaker.get("styles", [])
            style_id = pick_default_style_id(styles)
            if name and style_id is not None:
                speaker_map[name] = style_id
    except Exception as e:
        print(f"Warning: Could not fetch VOICEVOX speakers: {e}")

    SPEAKER_ID_CACHE = speaker_map
    return speaker_map

def resolve_speaker_id(speaker_name):
    if not speaker_name:
        speaker_name = DEFAULT_SPEAKER_NAME

    if speaker_name in SPEAKERS:
        return SPEAKERS[speaker_name]

    speaker_map = load_voicevox_speakers()
    if speaker_name in speaker_map:
        return speaker_map[speaker_name]

    if speaker_name != DEFAULT_SPEAKER_NAME:
        print(f"Warning: Speaker '{speaker_name}' not found. Using default speaker ID {DEFAULT_SPEAKER_ID}.")
    return DEFAULT_SPEAKER_ID

def safe_speaker_filename(speaker_name, speaker_id):
    if speaker_name in SPEAKER_EN_MAP:
        return SPEAKER_EN_MAP[speaker_name]

    ascii_name = re.sub(r"[^A-Za-z0-9]+", "_", speaker_name or "").strip("_").lower()
    if ascii_name:
        return ascii_name
    return f"speaker_{speaker_id}"

def generate_audio_file(text, speaker_name, output_filename, speaker_id=None):
    """
    VOICEVOX APIを使ってテキストから音声ファイルを生成する。
    1. audio_query を作成
    2. synthesis で音声合成
    """
    speaker_id = speaker_id if speaker_id is not None else resolve_speaker_id(speaker_name)
    tts_text = normalize_tts_text(text)

    # 1. Query Creation
    query_payload = {"text": tts_text, "speaker": speaker_id}
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
        speaker = line.get("speaker") or DEFAULT_SPEAKER_NAME
        text = line.get("text", "")
        speaker_id = resolve_speaker_id(speaker)

        # 安全なファイル名を生成
        safe_speaker = safe_speaker_filename(speaker, speaker_id)
        filename = os.path.join(output_dir, f"{i:03d}_{safe_speaker}.wav")

        print(f"[{i+1}/{len(dialogues)}] Generating {speaker}: {text[:20]}...")
        success = generate_audio_file(text, speaker, filename, speaker_id=speaker_id)

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
