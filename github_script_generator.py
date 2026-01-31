"""
GitHub リポジトリ変更点の台本生成モジュール
学術的議論に焦点を当てたPodcast形式の台本を生成
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


def format_date_jp(date_str):
    try:
        year, month, day = date_str.split("-")
        return f"{int(year)}年{int(month)}月{int(day)}日"
    except Exception:
        return date_str


def format_activities_text(activities):
    """
    アクティビティ情報をテキスト形式に整形
    学術的議論に関連する内容を抽出
    """
    text_parts = []

    # PRから学術的議論を抽出
    for pr in activities.get("pull_requests", []):
        body = pr.get("body", "") or ""
        comments_text = ""

        pr_text = f"""
【プルリクエスト #{pr['number']}】
タイトル: {pr['title']}
投稿者: {pr['author']}
状態: {pr['state']}
作成日: {pr['created_at'][:10] if pr.get('created_at') else '不明'}
URL: {pr['url']}
内容:
{body[:1500] if body else '説明なし'}
"""
        text_parts.append(pr_text)

    # Issueから議論を抽出
    for issue in activities.get("issues", []):
        body = issue.get("body", "") or ""

        comments_text = ""
        for comment in issue.get("comments", [])[:3]:
            comments_text += f"\n  - {comment['author']}: {comment['body'][:300]}"

        issue_text = f"""
【Issue #{issue['number']}】
タイトル: {issue['title']}
投稿者: {issue['author']}
状態: {issue['state']}
作成日: {issue['created_at'][:10] if issue.get('created_at') else '不明'}
ラベル: {', '.join(issue.get('labels', [])) or 'なし'}
URL: {issue['url']}
内容:
{body[:1000] if body else '説明なし'}
{('コメント:' + comments_text) if comments_text else ''}
"""
        text_parts.append(issue_text)

    # Discussionから議論を抽出
    for disc in activities.get("discussions", []):
        body = disc.get("body", "") or ""

        comments_text = ""
        for comment in disc.get("comments", [])[:3]:
            comments_text += f"\n  - {comment['author']}: {comment['body'][:300]}"

        disc_text = f"""
【Discussion #{disc['number']}】
タイトル: {disc['title']}
投稿者: {disc['author']}
カテゴリ: {disc.get('category', '不明')}
作成日: {disc['created_at'][:10] if disc.get('created_at') else '不明'}
URL: {disc['url']}
内容:
{body[:1000] if body else '説明なし'}
{('コメント:' + comments_text) if comments_text else ''}
"""
        text_parts.append(disc_text)

    # コミットのサマリー（主要な変更のみ）
    commits = activities.get("commits", [])
    if commits:
        commit_summary = "\n【主要なコミット】\n"
        for commit in commits[:10]:
            msg = commit.get("message", "").split("\n")[0]  # 1行目のみ
            commit_summary += f"- [{commit['sha']}] {msg}\n"
        text_parts.append(commit_summary)

    return "\n".join(text_parts)


def generate_github_script(activities, date_str=None):
    """
    GitHub アクティビティからPodcast台本を生成

    Args:
        activities: GitHub アクティビティ情報
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
    repo = activities.get("repo", "eegflow/eegflow.jp")

    # アクティビティの数を確認
    total_activities = (
        len(activities.get("pull_requests", [])) +
        len(activities.get("issues", [])) +
        len(activities.get("discussions", []))
    )

    if total_activities == 0:
        print("No significant activities found (only commits)")
        # コミットのみでも台本を生成
        if not activities.get("commits"):
            return None

    activities_text = format_activities_text(activities)

    system_prompt = f"""
あなたは人気Podcastの構成作家です。
提供されたGitHubリポジトリの変更情報を元に、リスナーが親しみやすく、かつ知的好奇心を刺激されるような「一人語りの台本」を作成してください。

話者は1人です：
1. 「{DEFAULT_SPEAKER_NAME}」: 落ち着いた丁寧語で話すナレーター。

【重要：学術的議論に焦点を当てる】
- コードの技術的な変更（バグ修正、リファクタリング等）ではなく、学術的・研究的な議論に焦点を当てる
- EEGや脳波研究に関する議論、新しい手法の提案、研究方法論についての議論を重点的に取り上げる
- 議論の背景、問題意識、提案されている解決策を分かりやすく解説する
- コミュニティでどのような議論が交わされているかを紹介する

【正確性ルール】
- 入力にない情報は推測で断定しない
- 不明な点は「詳細は議論を参照」と明記する
- 議論の要点を正確に伝える

【敬語の読み上げ】
- です・ます調で自然に話す
- スラッシュや括弧で敬語を省略しない

【読み上げやすさ】
- 英字略語や英単語は原則カタカナ表記に置き換える（例: EEG→イーイージー、GitHub→ギットハブ）
- アルファベット表記が避けられない固有名詞は、本文ではカタカナ読みのみを使う

【表記ルール】
- 日本語は通常の表記（漢字・ひらがな・カタカナ）で、ひらがなの分かち書きはしない
- 不要な空白を入れない
- 日付は「YYYY年M月D日」形式を使う

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

    # 台本の長さを調整
    if total_activities <= 2:
        min_lines = 10
        target_minutes = 5
    elif total_activities <= 5:
        min_lines = 8
        target_minutes = 8
    else:
        min_lines = 6
        target_minutes = 12

    user_prompt = f"""以下の{repo}リポジトリの変更情報を元に、約{target_minutes}分程度のトーク台本を作成してください。
日付は{jp_date_str}です。冒頭で日付と「イーイージーフロー開発日記」であることを紹介してください。

【重要】学術的・研究的な議論に焦点を当ててください：
- 新しい研究手法やアルゴリズムについての議論
- EEGデータの解析方法についての議論
- 論文や先行研究への言及
- 研究コミュニティでの議論や意見交換

技術的な実装の詳細（コードの変更、バグ修正等）は軽く触れる程度にして、
「なぜそのような変更が必要なのか」「どのような研究課題を解決しようとしているのか」に焦点を当ててください。

{activities_text}

台本の流れ:
1. オープニング（日付と番組紹介）
2. 主要な議論や変更の紹介（学術的観点から解説）
3. エンディング（まとめと次回予告）

各トピックについて：
- 背景・問題意識
- 議論の内容・提案
- 今後の展望や課題

構成指示：
- 各トピックにつき最低{min_lines}発話
- 1セリフは1〜2文で、読み上げやすい長さにする
"""

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
        "temperature": 0.5,
        "max_tokens": 4000,
        "stream": False
    }

    print(f"Generating GitHub activity script for {repo}...")
    print(f"Activities: {total_activities} (PRs: {len(activities.get('pull_requests', []))}, Issues: {len(activities.get('issues', []))}, Discussions: {len(activities.get('discussions', []))})")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1}/{max_retries}...")
            response = requests.post(LM_STUDIO_URL, headers=headers, json=payload, timeout=600)
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
                script_data["dialogue"] = cleaned_dialogue

            # 参考リンク情報を追加
            script_data['references'] = []
            for pr in activities.get("pull_requests", []):
                script_data['references'].append({
                    'type': 'PR',
                    'number': pr['number'],
                    'title': pr['title'],
                    'url': pr['url'],
                    'author': pr['author']
                })
            for issue in activities.get("issues", []):
                script_data['references'].append({
                    'type': 'Issue',
                    'number': issue['number'],
                    'title': issue['title'],
                    'url': issue['url'],
                    'author': issue['author']
                })
            for disc in activities.get("discussions", []):
                script_data['references'].append({
                    'type': 'Discussion',
                    'number': disc['number'],
                    'title': disc['title'],
                    'url': disc['url'],
                    'author': disc['author']
                })

            script_data['date'] = date_str
            script_data['repo'] = repo

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
    repo = script_data.get('repo', 'eegflow/eegflow.jp')
    references = script_data.get('references', [])

    description = f"""【{date_str}】EEGFlow 開発日記

本日の{repo}リポジトリの変更点と議論を、{DEFAULT_SPEAKER_NAME}が分かりやすく解説します。

━━━━━━━━━━━━━━━━━━━━━
📝 参考リンク
━━━━━━━━━━━━━━━━━━━━━
"""

    for ref in references:
        ref_type = ref.get('type', 'Link')
        description += f"""
【{ref_type} #{ref['number']}】{ref['title']}
投稿者: {ref['author']}
URL: {ref['url']}
"""

    description += f"""
━━━━━━━━━━━━━━━━━━━━━
🔗 リポジトリ
━━━━━━━━━━━━━━━━━━━━━
https://github.com/{repo}

━━━━━━━━━━━━━━━━━━━━━
🎙️ 出演
━━━━━━━━━━━━━━━━━━━━━
{DEFAULT_SPEAKER_NAME} (VOICEVOX)

#EEGFlow #EEG #脳波 #開発日記 #{DEFAULT_SPEAKER_NAME}
"""

    return description


if __name__ == "__main__":
    # テスト用
    test_activities = {
        "repo": "eegflow/eegflow.jp",
        "commits": [
            {"sha": "abc1234", "message": "Update EEG processing algorithm", "author": "test", "date": "", "url": "", "files_changed": []}
        ],
        "pull_requests": [
            {
                "number": 42,
                "title": "Add new ICA algorithm implementation",
                "body": "This PR implements a new Independent Component Analysis algorithm for EEG artifact removal...",
                "state": "open",
                "author": "researcher",
                "created_at": "2024-01-19T10:00:00Z",
                "updated_at": "2024-01-19T10:00:00Z",
                "merged_at": None,
                "url": "https://github.com/eegflow/eegflow.jp/pull/42",
                "labels": ["enhancement", "research"]
            }
        ],
        "issues": [],
        "discussions": []
    }

    script = generate_github_script(test_activities, "2024-01-19")
    if script:
        print(json.dumps(script, indent=2, ensure_ascii=False))
        print("\n--- Description ---")
        print(format_description(script))
