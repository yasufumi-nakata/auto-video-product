"""
Google Docsからコンテンツを読み込むモジュール (ファイル名のみベース)
APIを使用せず、ファイル名から日付とタイトルを取得
"""
import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Google Drive EEG-papersフォルダのパス（環境変数から取得）
GDRIVE_PAPERS_PATH = os.getenv("GDRIVE_PAPERS_PATH", "/Users/yasufumi/Library/CloudStorage/GoogleDrive-yasufumi@koparis.com/My Drive/2026/EEG-papers")


def parse_filename(filename):
    """
    ファイル名から日付とタイトル情報を抽出
    Format assumption: "Month Day, Year Time ... - Title.gdoc" or similar
    """
    # 日付パース: "January 2, 2026" のような形式を探す
    date_pattern = r"([A-Za-z]+)\s+(\d+),\s+(\d{4})"
    match = re.search(date_pattern, filename)

    published_date = None
    if match:
        month_str, day, year = match.groups()
        try:
            date_str = f"{month_str} {day}, {year}"
            published_date = datetime.strptime(date_str, "%B %d, %Y").date()
        except ValueError:
            pass

    # タイトル抽出: ファイル名そのものをタイトルとして扱う（拡張子除く）
    title = os.path.splitext(filename)[0]

    return published_date, title


def get_gdoc_papers(target_date=None):
    """
    EEG-papersフォルダのGdocファイル名から論文情報を取得
    API認証は一切行わない。

    Args:
        target_date: 取得する日付 (datetime.date)。Noneの場合は全て。
    """
    papers = []

    if not os.path.exists(GDRIVE_PAPERS_PATH):
        print(f"Warning: EEG-papers folder not found: {GDRIVE_PAPERS_PATH}")
        return papers

    print(f"Scanning Gdoc files in: {GDRIVE_PAPERS_PATH}")

    for filename in os.listdir(GDRIVE_PAPERS_PATH):
        if not filename.endswith('.gdoc'):
            continue

        file_date, title = parse_filename(filename)

        # 日付フィルタリング
        # ファイル名から日付が取れない場合はスキップ、またはtarget_date指定時は除外
        if target_date:
            if not file_date or file_date != target_date:
                continue

        # 中身は読めないので件名（ファイル名）を使用
        print(f"Found matching Gdoc: {filename}")

        papers.append({
            'source': 'Google Scholar Alert',
            'id': filename, # IDとしてファイル名を使用
            'title': title,
            'summary': f"Title from Google Drive: {title}",
            'url': "", # URLなし
            'doi': '',
            'authors': 'Google Scholar Alert',
            'published': str(file_date) if file_date else "Unknown",
            'pub_date_obj': datetime.combine(file_date, datetime.min.time()) if file_date else datetime.min,
            'full_content': f"Title from Google Drive: {title}"
        })

    return papers


if __name__ == "__main__":
    print("=== Testing Gdoc Reader (Filename Only) ===")
    papers = get_gdoc_papers()
    print(f"Found {len(papers)} papers")
    for p in papers:
        print(f"  Title: {p['title']}")
        print(f"  Date: {p['published']}")
