"""
論文紹介用の台本生成モジュール
複数の論文を紹介するPodcast形式の台本を生成
"""
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
SUMMARY_MAX_CHARS = int(os.getenv("PAPER_SUMMARY_MAX_CHARS", "1200"))
DIALOGUE_MAX_CHARS = int(os.getenv("PAPER_DIALOGUE_MAX_CHARS", "420"))
LM_STUDIO_TIMEOUT = int(os.getenv("LM_STUDIO_TIMEOUT", "240"))
LM_STUDIO_REWRITE_TIMEOUT = int(os.getenv("LM_STUDIO_REWRITE_TIMEOUT", "180"))
LM_STUDIO_REWRITE_BATCH_SIZE = int(os.getenv("LM_STUDIO_REWRITE_BATCH_SIZE", "5"))
LM_STUDIO_MAX_TOKENS = int(os.getenv("LM_STUDIO_MAX_TOKENS", "3200"))
DEFAULT_SPEAKER_NAME = os.getenv("VOICEVOX_SPEAKER_NAME", "青山龍星")
CJK_RANGE = r"\u3040-\u30ff\u3400-\u9fff"
SPACE_BETWEEN_CJK = re.compile(rf"(?<=[{CJK_RANGE}0-9])\s+(?=[{CJK_RANGE}0-9])")
SPACE_BETWEEN_CJK_ASCII = re.compile(rf"(?<=[{CJK_RANGE}])\s+(?=[A-Za-z0-9])")
SPACE_BETWEEN_ASCII_CJK = re.compile(rf"(?<=[A-Za-z0-9])\s+(?=[{CJK_RANGE}])")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?])")
SOFT_BREAK_CHARS = ["、", "，", ",", "・", "／", "/", " ", "　", "；", ";", ":", "："]
ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
SKIP_TAG_RE = re.compile(r"<skip>.*?</skip>", flags=re.DOTALL)
ENGLISH_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+\\-./]*")

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
    (
        re.compile(rf"(?<![A-Za-z0-9]){re.escape(abbr)}(?![A-Za-z0-9])"),
        reading,
        abbr,
    )
    for abbr, reading in ABBREVIATION_READINGS
]


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


def normalize_summary(summary):
    cleaned = " ".join((summary or "").split())
    if not cleaned:
        return "要約なし"
    if len(cleaned) > SUMMARY_MAX_CHARS:
        return cleaned[:SUMMARY_MAX_CHARS] + "..."
    return cleaned


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


def apply_abbreviation_readings(text):
    normalized = text
    for pattern, reading, abbr in ABBREVIATION_PATTERNS:
        normalized = pattern.sub(f"{reading}（<skip>{abbr}</skip>）", normalized)
    return normalized


def replace_outside_skip(text, repl_func):
    parts = []
    last = 0
    for match in SKIP_TAG_RE.finditer(text):
        parts.append(repl_func(text[last:match.start()]))
        parts.append(match.group(0))
        last = match.end()
    parts.append(repl_func(text[last:]))
    return "".join(parts)


def replace_outside_parentheses(text, repl_func):
    parts = []
    buf = ""
    depth = 0
    for ch in text:
        if ch == "（":
            if depth == 0:
                parts.append(("outside", buf))
                buf = ""
            depth += 1
            buf += ch
        elif ch == "）":
            if depth > 0:
                depth -= 1
            buf += ch
            if depth == 0:
                parts.append(("inside", buf))
                buf = ""
        else:
            buf += ch
    if buf:
        parts.append(("outside" if depth == 0 else "inside", buf))

    rebuilt = []
    for kind, chunk in parts:
        if kind == "outside":
            rebuilt.append(repl_func(chunk))
        else:
            rebuilt.append(chunk)
    return "".join(rebuilt)


def fallback_wrap_english(text):
    def repl(match):
        token = match.group(0)
        return f"英語表記（<skip>{token}</skip>）"
    def apply_rules(segment):
        return replace_outside_parentheses(segment, lambda s: ENGLISH_TOKEN_RE.sub(repl, s))
    return replace_outside_skip(text, apply_rules)


def split_long_text(text, max_chars):
    if not text:
        return []
    text = text.strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]

    sentences = [s for s in SENTENCE_SPLIT_RE.split(text) if s]
    chunks = []
    current = ""

    for sentence in sentences:
        if not current:
            if len(sentence) <= max_chars:
                current = sentence
            else:
                chunks.extend(force_split(sentence, max_chars))
        else:
            if len(current) + len(sentence) <= max_chars:
                current += sentence
            else:
                chunks.append(current)
                if len(sentence) <= max_chars:
                    current = sentence
                else:
                    chunks.extend(force_split(sentence, max_chars))
                    current = ""

    if current:
        chunks.append(current)

    return [c.strip() for c in chunks if c.strip()]


def force_split(text, max_chars):
    remaining = text.strip()
    chunks = []
    while remaining and len(remaining) > max_chars:
        cut = -1
        for ch in SOFT_BREAK_CHARS:
            idx = remaining.rfind(ch, 0, max_chars + 1)
            if idx > cut:
                cut = idx
        if cut <= 0:
            cut = max_chars
        chunk = remaining[:cut].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def split_dialogue_lines(dialogue, max_chars):
    if not dialogue:
        return []
    if max_chars <= 0:
        return dialogue
    split_lines = []
    for line in dialogue:
        if not isinstance(line, dict):
            continue
        speaker = line.get("speaker") or DEFAULT_SPEAKER_NAME
        text = normalize_dialogue_text(line.get("text", ""))
        for chunk in split_long_text(text, max_chars):
            normalized_chunk = normalize_dialogue_text(chunk)
            if normalized_chunk:
                split_lines.append({"speaker": speaker, "text": normalized_chunk})
    return split_lines


def rewrite_english_dialogue(dialogue):
    targets = []
    for idx, line in enumerate(dialogue):
        text = line.get("text", "")
        text = apply_abbreviation_readings(text)
        dialogue[idx]["text"] = text
        text_no_skip = SKIP_TAG_RE.sub("", text)
        if ASCII_LETTER_RE.search(text_no_skip):
            targets.append({"index": idx, "text": text})

    if not targets:
        return dialogue

    system_prompt = """
あなたは日本語の編集者です。
以下の台詞に含まれる英語・英字略語を、必ず日本語に言い換え、原文英語は <skip>English</skip> で後置してください。
表示上は括弧書きにしたい場合、例のようにします: 〇〇（<skip>Original English</skip>）
英語だけの文は禁止です。意味は変えず、情報を追加しないでください。
略語はカタカナ読み＋英字を <skip> </skip> で併記してください（例: イーイージー（<skip>EEG</skip>））。
"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    model = resolve_model()

    batch_size = max(1, LM_STUDIO_REWRITE_BATCH_SIZE)
    for start in range(0, len(targets), batch_size):
        batch = targets[start:start + batch_size]
        payload_json = json.dumps(batch, ensure_ascii=False)
        user_prompt = f"""次の台詞をルールに沿って書き換えてください。
JSON配列で返し、各要素は {{"index": 数字, "text": "修正後の台詞"}} の形式にしてください。
並び順は入力と同じにしてください。

対象台詞:
{payload_json}
"""

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 1200,
            "stream": False
        }

        try:
            response = requests.post(
                LM_STUDIO_URL,
                headers=headers,
                json=payload,
                timeout=LM_STUDIO_REWRITE_TIMEOUT
            )
            response.raise_for_status()
            result = response.json()
            content = result['choices'][0]['message']['content']
            content = content.replace("```json", "").replace("```", "").strip()
            start_idx = content.find('[')
            end_idx = content.rfind(']')
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx + 1]
            rewritten = json.loads(content)
            if isinstance(rewritten, list):
                for item in rewritten:
                    idx = item.get("index")
                    text = item.get("text")
                    if isinstance(idx, int) and 0 <= idx < len(dialogue) and isinstance(text, str):
                        dialogue[idx]["text"] = normalize_dialogue_text(text)
        except Exception as e:
            print(f"Warning: Failed to rewrite English dialogue batch: {e}")

    return dialogue


def format_date_jp(date_str):
    try:
        year, month, day = date_str.split("-")
        return f"{int(year)}年{int(month)}月{int(day)}日"
    except Exception:
        return date_str


def generate_paper_script(papers, date_str=None):
    """
    複数の論文情報からPodcast台本を生成

    Args:
        papers: 論文情報のリスト
        date_str: 日付文字列（例: "2024-01-19"）

    Returns:
        dict: 台本データ（title, dialogue, references）
    """
    if not ensure_lm_studio_ready():
        print("LM Studio is not available. Script generation aborted.")
        return None
    if date_str is None:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")

    jp_date_str = format_date_jp(date_str)

    # 論文情報を整形
    papers_text = ""
    for i, paper in enumerate(papers, 1):
        summary = normalize_summary(paper.get("summary"))
        doi = paper.get("doi") or "なし"
        published = paper.get("published") or "不明"
        papers_text += f"""
【論文{i}】
タイトル: {paper.get('title', 'No Title')}
著者: {paper.get('authors', 'Unknown')}
出典: {paper.get('source', 'Unknown')}
公開日: {published}
URL: {paper.get('url', '')}
DOI: {doi}
要約: {summary}
"""

    system_prompt = f"""
あなたは人気Podcastの構成作家です。
提供された論文情報を元に、リスナーが親しみやすく、かつ知的好奇心を刺激されるような「一人語りの台本」を作成してください。

話者は1人です：
1. 「{DEFAULT_SPEAKER_NAME}」: 落ち着いた丁寧語で話すナレーター。

【正確性ルール】
- 入力にない情報は推測で断定しない
- 数値/データセット/手法名/固有名詞は要約にあるもののみ使用する
- 不明な点は「要約からは不明」と明記する

【敬語の読み上げ】
- です・ます調で自然に話す
- スラッシュや括弧で敬語を省略しない

【英語処理ルール】
- 英語は必ず日本語に言い換え、原文英語は <skip>English</skip> として後置する
- 表示上は括弧書きにしたい場合、例のようにする: 畳み込みニューラルネットワーク（<skip>Convolutional Neural Network</skip>）
- 英字略語はカタカナ読み＋英字を <skip> </skip> で併記する（例: イーイージー（<skip>EEG</skip>））
- 英語だけの文は禁止
- 日本語訳が難しい場合は、カタカナ読み＋<skip>英語</skip>にする

【表記ルール】
- 日本語は通常の表記（漢字・ひらがな・カタカナ）で、ひらがなの分かち書きはしない
- 不要な空白を入れない
- 日付は「YYYY年M月D日」形式を使う
 - 1セリフは最大{DIALOGUE_MAX_CHARS}文字程度に収める

【重要】出力は必ず以下のJSONフォーマットのみにしてください。
Markdownのコードブロック(```json)や、冒頭・末尾の挨拶、解説は一切不要です。
JSONの文法エラー（カンマ漏れ、閉じていない引用符など）がないように注意してください。

Format:
{{
  "title": "エピソードのタイトル",
  "dialogue": [
    {{"speaker": "{DEFAULT_SPEAKER_NAME}", "text": "台詞"}}
  ]
}}
"""

    paper_count = len(papers)
    if paper_count <= 4:
        min_lines = 8
    elif paper_count <= 7:
        min_lines = 7
    else:
        min_lines = 6
    target_minutes = min(15, max(10, paper_count + 5))

    user_prompt = f"""以下の論文情報を元に、約{target_minutes}分程度の論文紹介トーク台本を作成してください。
日付は{jp_date_str}です。冒頭で日付と「今日のEEG論文まとめ」であることを紹介してください。

各論文について：
- 背景・先行研究の位置づけ（要約にない場合は「要約からは不明」と明記）
- 研究の目的・課題
- 手法・データ・対象
- 主な結果や示唆
- 限界・今後の展望（要約にない場合は明記）

構成指示：
- 論文の順番は入力順を厳守
- 各論文につき最低{min_lines}発話
- 1セリフは1〜2文で、読み上げやすい長さにする
- 要点の言い換えや独り言の確認を挟み、少し長めにする（要約にある範囲で）
- 推測で断定しない

{papers_text}

台本の流れ:
1. オープニング（日付と番組紹介）
2. 各論文の紹介（要点を整理しながら一人語りで解説）
3. エンディング（まとめと次回予告）
"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    model = resolve_model()
    max_tokens = min(LM_STUDIO_MAX_TOKENS, 800 + (len(papers) * 250))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.5,
        "max_tokens": max_tokens,
        "stream": False
    }

    print(f"Generating paper review script for {len(papers)} papers...")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1}/{max_retries}...")
            response = requests.post(LM_STUDIO_URL, headers=headers, json=payload, timeout=LM_STUDIO_TIMEOUT)
            response.raise_for_status()

            result = response.json()
            content = result['choices'][0]['message']['content']

            # JSON部分を抽出
            content = content.replace("```json", "").replace("```", "").strip()
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
                rewritten_dialogue = rewrite_english_dialogue(cleaned_dialogue)
                for line in rewritten_dialogue:
                    text = line.get("text", "")
                    text_no_skip = SKIP_TAG_RE.sub("", text)
                    if ASCII_LETTER_RE.search(text_no_skip):
                        line["text"] = normalize_dialogue_text(fallback_wrap_english(text))
                script_data["dialogue"] = split_dialogue_lines(rewritten_dialogue, DIALOGUE_MAX_CHARS)

            # 参考文献情報を追加
            script_data['references'] = []
            for paper in papers:
                ref = {
                    'title': paper['title'],
                    'authors': paper['authors'],
                    'url': paper['url'],
                    'doi': paper.get('doi', ''),
                    'source': paper['source'],
                    'published': paper['published']
                }
                script_data['references'].append(ref)

            script_data['date'] = date_str

            return script_data

        except json.JSONDecodeError:
            print("Error: LM Studio response was not valid JSON.")
            if attempt < max_retries - 1:
                print("Retrying...")
            else:
                print("Raw response:", content[:500])
                return None
        except Exception as e:
            print(f"Error communicating with LM Studio: {e}")
            if attempt < max_retries - 1:
                print("Retrying...")
            else:
                return None

    return None


def format_description(script_data):
    """
    YouTube概要欄用のテキストを生成
    """
    date_str = script_data.get('date', '')
    references = script_data.get('references', [])

    description = f"""【{date_str}】EEGの論文まとめ

本日のEEG・脳波関連論文を、{DEFAULT_SPEAKER_NAME}が分かりやすく解説します。

━━━━━━━━━━━━━━━━━━━━━
📚 参考論文
━━━━━━━━━━━━━━━━━━━━━
"""

    for i, ref in enumerate(references, 1):
        description += f"""
【{i}】{ref['title']}
著者: {ref['authors']}
出典: {ref['source']}
URL: {ref['url']}
"""
        if ref.get('doi'):
            description += f"DOI: {ref['doi']}\n"

    description += """
━━━━━━━━━━━━━━━━━━━━━
🎙️ 出演
━━━━━━━━━━━━━━━━━━━━━
{DEFAULT_SPEAKER_NAME} (VOICEVOX)

#EEG #脳波 #論文紹介 #{DEFAULT_SPEAKER_NAME}
"""

    return description


if __name__ == "__main__":
    # テスト用
    test_papers = [
        {
            'title': 'Deep Learning for EEG-based Emotion Recognition',
            'authors': 'John Smith, Jane Doe',
            'source': 'arXiv',
            'url': 'https://arxiv.org/abs/2401.00001',
            'doi': '',
            'summary': 'This paper proposes a novel deep learning approach for emotion recognition using EEG signals...',
            'published': '2024-01-19'
        }
    ]

    script = generate_paper_script(test_papers, "2024-01-19")
    if script:
        print(json.dumps(script, indent=2, ensure_ascii=False))
        print("\n--- Description ---")
        print(format_description(script))
