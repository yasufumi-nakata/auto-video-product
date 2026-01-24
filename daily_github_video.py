"""
Daily GitHub Video Generator Service
eegflow.jp の GitHub リポジトリの変更点を取得し、学術的議論に焦点を当てた動画を生成・アップロード
"""
import time
import datetime
import os
import shutil
import argparse
import json
from datetime import timedelta
from dotenv import load_dotenv

# Import our modules
from github_fetcher import fetch_all_activities
from github_script_generator import generate_github_script, format_description
from audio_generator import process_script
from simple_image_gen import generate_thumbnail
from video_editor import create_podcast_video
from youtube_uploader import upload_video

# Load environment variables
load_dotenv()

# Configuration
TARGET_HOUR = 11  # 11:00 AM JST (論文動画の後)
TARGET_MINUTE = 0
GITHUB_REPO = os.getenv("GITHUB_REPO", "eegflow/eegflow.jp")


def get_unique_path(path):
    """Return a non-colliding path by adding a _vN suffix if needed."""
    if not os.path.exists(path):
        return path

    base, ext = os.path.splitext(path)
    for i in range(2, 100):
        candidate = f"{base}_v{i}{ext}"
        if not os.path.exists(candidate):
            return candidate

    timestamp = datetime.datetime.now().strftime("%H%M%S")
    return f"{base}_{timestamp}{ext}"


def cleanup_temp_files():
    """Clean up temporary files from previous runs."""
    extensions = ['.mp3', '.wav', '.png', '.mp4', '.json']
    prefixes_to_delete = ['temp_', 'speech_', 'github_script', 'github_thumbnail']

    for filename in os.listdir('.'):
        if any(filename.endswith(ext) for ext in extensions):
            if any(filename.startswith(prefix) for prefix in prefixes_to_delete):
                try:
                    os.remove(filename)
                except OSError:
                    pass

    if os.path.exists('github_output_audio'):
        shutil.rmtree('github_output_audio', ignore_errors=True)


def wait_until_target_time(target_hour, target_minute, force_next_day=False):
    """Wait until the target time (JST)."""
    now = datetime.datetime.now()
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

    if force_next_day or now >= target:
        target = target + datetime.timedelta(days=1)

    wait_seconds = (target - now).total_seconds()
    print(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Next run scheduled at: {target.strftime('%Y-%m-%d %H:%M:%S')} (waiting {wait_seconds/3600:.1f} hours)")

    return wait_seconds


def generate_github_video(test_mode=False, days_back=1, target_date=None, repo=None):
    """
    Main workflow for GitHub video generation.

    Args:
        test_mode: テストモード（YouTube投稿をスキップ）
        days_back: 何日前までの変更を取得するか
        target_date: 特定の日付を指定
        repo: リポジトリ名（owner/repo形式）
    """
    print(f"\n==================================================")

    if repo is None:
        repo = GITHUB_REPO

    if target_date:
        today = target_date
        print(f"=== GitHub Video Generation for: {today} (Manual Override) ===")
    else:
        today = datetime.date.today()
        print(f"=== GitHub Video Generation for: {today} ===")

    print(f"Repository: {repo}")

    # 1. Fetch GitHub Activities
    print(f"\n=== Phase 1: Fetching GitHub Activities for {repo} ===")

    activities = fetch_all_activities(repo=repo, days_back=days_back)

    total_items = (
        len(activities.get("commits", [])) +
        len(activities.get("pull_requests", [])) +
        len(activities.get("issues", [])) +
        len(activities.get("discussions", []))
    )

    print(f"Total activities: {total_items}")

    if total_items == 0:
        print("No activities found in the repository.")
        return None

    # 議論（PR, Issue, Discussion）がない場合は警告
    discussion_items = (
        len(activities.get("pull_requests", [])) +
        len(activities.get("issues", [])) +
        len(activities.get("discussions", []))
    )
    if discussion_items == 0:
        print("Warning: No discussions found (only commits). Video may be short.")

    # 2. Generate Script
    print("\n=== Phase 2: Generating Script ===")
    date_str = str(today)
    script_data = generate_github_script(activities, date_str=date_str)
    if not script_data:
        print("Failed to generate script.")
        return None

    # Save script to file for audio generator
    script_file = "github_script.json"
    with open(script_file, "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=2, ensure_ascii=False)
    print(f"Script saved to {script_file}")

    # 3. Generate Audio
    print("\n=== Phase 3: Generating Audio ===")
    audio_folder = "github_output_audio"
    audio_paths = process_script(script_file, audio_folder)
    if not audio_paths:
        print("Failed to generate audio.")
        return None

    # 4. Generate Thumbnail
    print("\n=== Phase 4: Generating Thumbnail ===")
    title = script_data.get("title", f"EEGFlow Development Diary {today}")
    thumbnail_prompt = f"EEG brain wave research development, programming code, GitHub, scientific visualization, {title}"

    thumbnail_path = generate_thumbnail(thumbnail_prompt, output_filename="github_thumbnail.png")
    if not thumbnail_path:
        print("Failed to generate thumbnail. Using fallback/black image might happen.")

    # 5. Create Video
    print("\n=== Phase 5: Creating Video ===")
    video_path = f"github_video_{today}.mp4"
    if test_mode:
        video_path = f"test_github_video_{today}.mp4"

    video_path = get_unique_path(video_path)

    final_video = create_podcast_video(
        thumbnail_path,
        audio_folder,
        video_path,
        script_file=script_file
    )

    if not final_video:
        print("Failed to create video.")
        return None

    # 6. Upload to YouTube
    print("\n=== Phase 6: Uploading to YouTube ===")

    video_title = f"EEGFlow開発日記 {today} | GitHub更新まとめ"
    if test_mode:
        video_title = f"[TEST] {video_title}"

    description = format_description(script_data)

    try:
        video_id = upload_video(
            file_path=final_video,
            title=video_title,
            description=description,
            category_id="28",  # Science & Technology
            keywords=["EEGFlow", "EEG", "脳波", "開発日記", "GitHub", "Neuroscience", "BCI"],
            privacy_status="public" if not test_mode else "private"
        )
        print(f"Video uploaded successfully! ID: {video_id}")
        print(f"URL: https://youtu.be/{video_id}")
    except Exception as e:
        print(f"Failed to upload video: {e}")

    return final_video


def run_service(test_mode=False, repo=None):
    """
    Run as a service, executing daily at 11:00 JST.
    """
    print(f"Starting GitHub Video Service (Target: 11:00 JST)")
    print(f"Repository: {repo or GITHUB_REPO}")

    while True:
        wait_seconds = wait_until_target_time(TARGET_HOUR, TARGET_MINUTE)
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        print("\nWake up! Starting GitHub video generation...")
        try:
            cleanup_temp_files()
            generate_github_video(test_mode=test_mode, repo=repo)
        except Exception as e:
            print(f"Error during GitHub video generation: {e}")
        time.sleep(60)


def run_once(test_mode=False, days_back=1, repo=None):
    """Run once immediately and exit."""
    cleanup_temp_files()
    return generate_github_video(test_mode=test_mode, days_back=days_back, repo=repo)


def run_once_tomorrow(test_mode=False, repo=None):
    """Wait until next target time and run once."""
    wait_seconds = wait_until_target_time(TARGET_HOUR, TARGET_MINUTE, force_next_day=True)
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    return run_once(test_mode=test_mode, repo=repo)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily GitHub Video Generator Service")
    parser.add_argument("--test", action="store_true", help="Run in test mode (private upload)")
    parser.add_argument("--once", action="store_true", help="Run once immediately and exit")
    parser.add_argument("--tomorrow", action="store_true", help="Run once at the next 11:00 (tomorrow) and exit")
    parser.add_argument("--days", type=int, default=1, help="Number of days back to fetch activities (default: 1)")
    parser.add_argument("--repo", type=str, help="Repository name in owner/repo format (default: from env)")

    args = parser.parse_args()

    if args.tomorrow:
        run_once_tomorrow(test_mode=args.test, repo=args.repo)
    elif args.once:
        run_once(test_mode=args.test, days_back=args.days, repo=args.repo)
    else:
        run_service(test_mode=args.test, repo=args.repo)
