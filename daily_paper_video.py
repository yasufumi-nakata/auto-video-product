"""
Daily Paper Video Generator Service
Fetches papers from arXiv/Scopus, generates script, audio, thumbnail, video, and uploads to YouTube.
Runs daily at 10:00 JST.
"""
import time
import datetime
import os
import shutil
import argparse
import sys
import json
from datetime import timedelta
from dotenv import load_dotenv

# Import our modules
from paper_fetcher import fetch_papers
from paper_script_generator import generate_paper_script
from audio_generator import process_script
from simple_image_gen import generate_thumbnail
from video_editor import create_podcast_video
from youtube_uploader import upload_video

# Load environment variables
load_dotenv()

# Configuration
TARGET_HOUR = 10  # 10:00 AM JST
TARGET_MINUTE = 0

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
    for filename in os.listdir('.'):
        if any(filename.endswith(ext) for ext in extensions):
            if filename.startswith('temp_') or filename.startswith('speech_') or filename == 'script.json' or filename == 'thumbnail.png':
                try:
                    os.remove(filename)
                except OSError:
                    pass

    if os.path.exists('output_audio'):
        shutil.rmtree('output_audio', ignore_errors=True)

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

def normalize_target_date(target_date):
    if not target_date:
        return None
    if isinstance(target_date, datetime.date):
        return target_date
    if isinstance(target_date, str):
        try:
            return datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def generate_daily_video(test_mode=False, max_papers=None, target_date=None):
    """
    Main workflow for daily video generation.
    """
    print(f"\n==================================================")

    target_date = normalize_target_date(target_date)
    if target_date:
        today = target_date
        print(f"=== Paper Video Generation for: {today} (Manual Override) ===")
    else:
        today = datetime.date.today()
        print(f"=== Paper Video Generation for: {today} ===")

    # 1. Fetch Papers
    print(f"\n=== Phase 1: Fetching Papers for {today} ===")

    max_results = max_papers if max_papers and max_papers > 0 else None
    days_back = 1
    if target_date:
        days_back = (datetime.date.today() - target_date).days
        if days_back < 0:
            print("Target date is in the future. Aborting.")
            return
    all_papers = fetch_papers(max_results=max_results, days_back=days_back, target_date=today)
    if max_papers and max_papers > 0 and len(all_papers) > max_papers:
        all_papers = all_papers[:max_papers]

    print(f"Total papers: {len(all_papers)}")

    if not all_papers:
        print("No papers found from any source.")
        return

    # 4. Generate Script
    print("\n=== Phase 2: Generating Script ===")
    script_data = generate_paper_script(all_papers, date_str=str(today))
    if not script_data:
        print("Failed to generate script.")
        return

    # Save script to file for audio generator
    with open("script.json", "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=2, ensure_ascii=False)
    print("Script saved to script.json")

    # 5. Generate Audio
    print("\n=== Phase 3: Generating Audio ===")
    audio_paths = process_script("script.json", "output_audio")
    if not audio_paths:
        print("Failed to generate audio.")
        return

    # 6. Generate Thumbnail
    print("\n=== Phase 4: Generating Thumbnail ===")
    if all_papers:
        title_for_prompt = all_papers[0]['title']
    else:
        title_for_prompt = f"Brain Computer Interface News {today}"

    thumbnail_path = generate_thumbnail(title_for_prompt)
    if not thumbnail_path:
        print("Failed to generate thumbnail. Using fallback/black image might happen.")

    # 7. Create Video
    print("\n=== Phase 5: Creating Video ===")
    video_path = f"daily_news_{today}.mp4"
    if test_mode:
        video_path = f"test_video_{today}.mp4"

    video_path = get_unique_path(video_path)

    # Corrected arguments: image_path, audio_folder, output_filename, script_file
    final_video = create_podcast_video(thumbnail_path, "output_audio", video_path, script_file="script.json")

    if not final_video:
        print("Failed to create video.")
        return

    # 8. Upload to YouTube (Always upload)
    print("\n=== Phase 6: Uploading to YouTube ===")
    title = f"Brain Tech News {today} | New EEG & BCI Papers"
    if test_mode:
        title = f"[TEST] {title}"

    description = f"Daily summary of the latest EEG and BCI research papers selected from arXiv and Scopus.\n\nDate: {today}\n\nPapers covered:\n"
    for p in all_papers:
        description += f"- {p['title']}\n  {p['url']}\n"

    try:
        video_id = upload_video(
            file_path=final_video,
            title=title,
            description=description,
            category_id="28", # Science & Technology
            keywords=["EEG", "BCI", "Neuroscience", "Brain Computer Interface", "AI", "Research"],
            privacy_status="public"
        )
        print(f"Video uploaded successfully! ID: {video_id}")
        print(f"URL: https://youtu.be/{video_id}")
    except Exception as e:
        print(f"Failed to upload video: {e}")

    return final_video

def run_service(test_mode=False):
    """
    Run as a service, executing daily at 10:00 JST.
    """
    print(f"Starting Brain Paper Video Service (Target: 10:00 JST)")

    while True:
        wait_seconds = wait_until_target_time(TARGET_HOUR, TARGET_MINUTE)
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        print("\nWake up! Starting daily video generation...")
        try:
            cleanup_temp_files()
            generate_daily_video(test_mode=test_mode)
        except Exception as e:
            print(f"Error during daily generation: {e}")
        time.sleep(60)

def run_once(test_mode=False, max_papers=None, target_date=None):
    cleanup_temp_files()
    return generate_daily_video(test_mode=test_mode, max_papers=max_papers, target_date=target_date)

def run_once_tomorrow(test_mode=False, max_papers=None):
    wait_seconds = wait_until_target_time(TARGET_HOUR, TARGET_MINUTE, force_next_day=True)
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    return run_once(test_mode=test_mode, max_papers=max_papers)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily Paper Video Generator Service")
    parser.add_argument("--test", action="store_true", help="Run in test mode (no upload, verbose output)")
    parser.add_argument("--once", action="store_true", help="Run once immediately and exit")
    parser.add_argument("--tomorrow", action="store_true", help="Run once at the next 10:00 (tomorrow) and exit")
    parser.add_argument("--papers", type=int, help="Max number of papers to process (for testing)")
    parser.add_argument("--date", type=str, help="Target date in YYYY-MM-DD (manual generation)")

    args = parser.parse_args()

    if args.tomorrow:
        success = bool(run_once_tomorrow(test_mode=args.test, max_papers=args.papers))
        sys.exit(0 if success else 1)
    elif args.once:
        success = bool(run_once(test_mode=args.test, max_papers=args.papers, target_date=args.date))
        sys.exit(0 if success else 1)
    else:
        run_service(test_mode=args.test)
