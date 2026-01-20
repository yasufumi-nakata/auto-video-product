"""
Google Drive EEG-papersフォルダの論文記録を管理するモジュール
既に処理済みの論文をトラッキングして重複を避ける
"""
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Google Drive EEG-papersフォルダのパス（環境変数から取得）
GDRIVE_PAPERS_PATH = os.getenv("GDRIVE_PAPERS_PATH", "/Users/yasufumi/Library/CloudStorage/GoogleDrive-yasufumi@koparis.com/My Drive/2026/EEG-papers")


def parse_date_from_filename(filename):
    """
    ファイル名から日付を抽出
    例: "January 19, 2026 at 2 AM JST 脳波; 言語: 英語, 日本語 - 新しい結果.gdoc"
    """
    pattern = r"([A-Za-z]+)\s+(\d+),\s+(\d{4})"
    match = re.search(pattern, filename)
    if match:
        month_str, day, year = match.groups()
        try:
            date_str = f"{month_str} {day}, {year}"
            return datetime.strptime(date_str, "%B %d, %Y").date()
        except ValueError:
            pass
    return None


def get_processed_dates():
    """EEG-papersフォルダ内のファイルから処理済みの日付リストを取得"""
    processed_dates = set()

    if not os.path.exists(GDRIVE_PAPERS_PATH):
        print(f"Warning: EEG-papers folder not found: {GDRIVE_PAPERS_PATH}")
        return processed_dates

    for filename in os.listdir(GDRIVE_PAPERS_PATH):
        date = parse_date_from_filename(filename)
        if date:
            processed_dates.add(date)

    return processed_dates


def get_unprocessed_dates(days_to_check=7):
    """まだ処理されていない過去の日付を取得"""
    processed = get_processed_dates()
    today = datetime.now().date()

    unprocessed = []
    for i in range(1, days_to_check + 1):
        check_date = today - timedelta(days=i)
        if check_date not in processed:
            unprocessed.append(check_date)

    unprocessed.sort()
    return unprocessed


if __name__ == "__main__":
    print("=== Paper Tracker ===")
    processed = get_processed_dates()
    print(f"Processed dates: {len(processed)}")
    for d in sorted(processed):
        print(f"  - {d}")

    print("\n=== Unprocessed dates (last 7 days) ===")
    for d in get_unprocessed_dates(7):
        print(f"  - {d}")
