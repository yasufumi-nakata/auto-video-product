"""
毎日10時にEEG論文紹介動画を自動生成・アップロードするスクリプト
"""
import os
import sys
import json
import shutil
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# 自作モジュールをインポート
from paper_fetcher import fetch_papers, SEARCH_QUERY
from paper_script_generator import generate_paper_script, format_description
from audio_generator import process_script
from simple_image_gen import generate_thumbnail
from video_editor import create_podcast_video
from youtube_uploader import upload_video


def wait_until_target_time(target_hour=10, target_minute=0):
    """指定時刻まで待機"""
    now = datetime.now()
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

    if now >= target:
        target = target + timedelta(days=1)

    wait_seconds = (target - now).total_seconds()
    print(f"Next run scheduled at {target.strftime('%Y-%m-%d %H:%M:%S')} (waiting {wait_seconds:.0f}s)")
    return wait_seconds


def cleanup_temp_files():
    """一時ファイルを削除"""
    files_to_remove = ["script.json", "thumbnail.png", "final_video.mp4"]
    folders_to_remove = ["output_audio"]

    for f in files_to_remove:
        if os.path.exists(f):
            os.remove(f)
            print(f"Removed: {f}")

    for folder in folders_to_remove:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"Removed folder: {folder}")


def generate_daily_video(test_mode=False, max_papers=3):
    """
    1日分の論文紹介動画を生成してアップロード

    Args:
        test_mode: Trueの場合、アップロードをスキップ
        max_papers: 取得する論文の最大数
    """
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*50}")
    print(f"=== Daily Paper Video Generation: {today} ===")
    print(f"{'='*50}\n")

    # 1. 論文を取得
    print("=== Phase 1: Fetching Papers ===")
    papers = fetch_papers(max_results=max_papers)

    if not papers:
        print("No papers found. Skipping video generation.")
        return None

    print(f"Found {len(papers)} papers")

    # 2. 台本を生成
    print("\n=== Phase 2: Generating Script ===")
    script = generate_paper_script(papers, today)

    if not script:
        print("Failed to generate script.")
        return None

    # 台本を保存
    with open("script.json", "w", encoding="utf-8") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)
    print("Script saved to script.json")

    # 3. 音声を生成
    print("\n=== Phase 3: Generating Audio ===")
    audio_files = process_script("script.json", "output_audio")

    if not audio_files:
        print("Failed to generate audio.")
        return None

    # 4. サムネイルを生成
    print("\n=== Phase 4: Generating Thumbnail ===")
    title = script.get("title", "EEG論文まとめ")
    prompt = f"masterpiece, best quality, anime style, a futuristic brain research laboratory with a cute green haired anime girl and a pink haired elegant anime girl discussing EEG brain waves data on holographic screens, scientific atmosphere, highly detailed, 4k"
    thumbnail_path = generate_thumbnail(prompt, "thumbnail.png")

    if not thumbnail_path:
        print("Failed to generate thumbnail.")
        return None

    # 5. 動画を生成（字幕付き）
    print("\n=== Phase 5: Creating Video with Subtitles ===")
    video_path = create_podcast_video(
        thumbnail_path,
        "output_audio",
        "final_video.mp4",
        script_file="script.json"
    )

    if not video_path:
        print("Failed to create video.")
        return None

    # 6. YouTubeにアップロード
    if not test_mode:
        print("\n=== Phase 6: Uploading to YouTube ===")

        # タイトルと概要欄を作成
        video_title = f"【{today}】EEGの論文まとめ - {title}"
        if len(video_title) > 100:
            video_title = video_title[:97] + "..."

        description = format_description(script)

        video_id = upload_video(
            video_path,
            video_title,
            description,
            privacy_status="public"
        )

        if video_id:
            print(f"\nUpload Complete! Video ID: {video_id}")
            print(f"URL: https://www.youtube.com/watch?v={video_id}")
            return video_id
        else:
            print("Upload failed.")
            return None
    else:
        print("\n=== Test Mode: Skipping Upload ===")
        print(f"Video created: {video_path}")
        print(f"Title would be: 【{today}】EEGの論文まとめ - {title}")
        return "test_mode"


def run_service(test_mode=False):
    """
    毎日10時に動画を生成するサービスを起動
    """
    print("=== Daily Paper Video Service (10:00 AM) ===")
    print(f"Search Query: {SEARCH_QUERY}")

    while True:
        try:
            # 動画生成を実行
            result = generate_daily_video(test_mode=test_mode)

            if result:
                print(f"\nDaily video generation completed: {result}")
            else:
                print("\nDaily video generation failed or skipped.")

            # テストモードの場合は1回で終了
            if test_mode:
                print("Test run complete.")
                break

            # 一時ファイルをクリーンアップ
            cleanup_temp_files()

            # 次の10時まで待機
            wait_seconds = wait_until_target_time(10, 0)
            time.sleep(wait_seconds)

        except Exception as e:
            print(f"Error during video generation: {e}")
            import traceback
            traceback.print_exc()

            if test_mode:
                break

            # エラー時は1時間後にリトライ
            print("Retrying in 1 hour...")
            time.sleep(3600)


def run_once(test_mode=False, max_papers=3):
    """
    1回だけ実行（テスト用）
    """
    return generate_daily_video(test_mode=test_mode, max_papers=max_papers)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Daily Paper Video Generator")
    parser.add_argument("--test", action="store_true", help="Test mode (no upload)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--papers", type=int, default=3, help="Number of papers to include")
    args = parser.parse_args()

    if args.once:
        run_once(test_mode=args.test, max_papers=args.papers)
    else:
        run_service(test_mode=args.test)
