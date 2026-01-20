"""
論文紹介用の台本生成モジュール
複数の論文を紹介するPodcast形式の台本を生成
"""
import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

LM_STUDIO_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1") + "/chat/completions"
API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")


def generate_paper_script(papers, date_str=None):
    """
    複数の論文情報からPodcast台本を生成

    Args:
        papers: 論文情報のリスト
        date_str: 日付文字列（例: "2024-01-19"）

    Returns:
        dict: 台本データ（title, dialogue, references）
    """
    if date_str is None:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")

    # 論文情報を整形
    papers_text = ""
    for i, paper in enumerate(papers, 1):
        papers_text += f"""
【論文{i}】
タイトル: {paper['title']}
著者: {paper['authors']}
出典: {paper['source']}
URL: {paper['url']}
要約: {paper['summary'][:500]}...
"""

    system_prompt = """
あなたは人気Podcastの構成作家です。
提供された論文情報を元に、リスナーが親しみやすく、かつ知的好奇心を刺激されるような「対話形式の台本」を作成してください。

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
    {"speaker": "ずんだもん", "text": "台詞"},
    {"speaker": "四国めたん", "text": "台詞"}
  ]
}
"""

    user_prompt = f"""以下の論文情報を元に、約3〜5分程度の論文紹介トーク台本を作成してください。
日付は{date_str}です。冒頭で日付と「今日のEEG論文まとめ」であることを紹介してください。

各論文について：
- 研究の目的と背景を簡潔に紹介
- 主な発見や結果を説明
- 研究の意義や今後の展望を述べる

{papers_text}

台本の流れ:
1. オープニング（日付と番組紹介）
2. 各論文の紹介（ずんだもんが興味を持ち、めたんが解説）
3. エンディング（まとめと次回予告）
"""

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
        "max_tokens": 4000,
        "stream": False
    }

    print(f"Generating paper review script for {len(papers)} papers...")

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

本日のEEG・脳波関連論文を、ずんだもんと四国めたんが分かりやすく解説します。

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
ずんだもん / 四国めたん (VOICEVOX)

#EEG #脳波 #論文紹介 #ずんだもん #四国めたん
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
