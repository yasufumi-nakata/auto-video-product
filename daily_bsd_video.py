"""
Daily Brain Science Dictionary Video Generator
Fetches new items from BSD, generates explanatory videos.
"""
import time
import datetime
import os
import shutil
import argparse
import json
import sys
from dotenv import load_dotenv

# Import modules
from bsd_fetcher import fetch_recent_items_list, fetch_article_content
from bsd_script_generator import generate_bsd_script
from audio_generator import process_script
from simple_image_gen import generate_thumbnail
from video_editor import create_podcast_video
from youtube_uploader import upload_video

load_dotenv()

TARGET_HOURS = [14, 17] # 14:00 and 17:00
STATE_FILE = "bsd_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {"seen_urls": []}
    return {"seen_urls": []}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def get_unique_path(path):
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
    extensions = ['.mp3', '.wav', '.png', '.mp4', '.json']
    prefixes = ['temp_', 'speech_', 'bsd_script', 'bsd_thumbnail']
    for filename in os.listdir('.'):
        if any(filename.endswith(ext) for ext in extensions):
            if any(filename.startswith(prefix) for prefix in prefixes):
                try:
                    os.remove(filename)
                except OSError:
                    pass
    if os.path.exists('bsd_output_audio'):
        shutil.rmtree('bsd_output_audio', ignore_errors=True)

def generate_bsd_video(test_mode=False, force_url=None):
    print(f"\n=== BSD Video Generation Start ===")
    
    # 1. Fetch Items
    items = fetch_recent_items_list()
    if not items:
        print("No items found.")
        return

    state = load_state()
    seen_urls = set(state.get("seen_urls", []))
    
    target_item = None
    
    if force_url:
        # Find the item with this URL
        for item in items:
            if item['url'] == force_url:
                target_item = item
                break
        if not target_item:
            print(f"URL not found in recent items, but fetching anyway: {force_url}")
            target_item = {'title': 'Unknown', 'url': force_url}
    else:
        # Find first unseen item
        for item in items:
            if item['url'] not in seen_urls:
                target_item = item
                break
    
    if not target_item:
        print("No new items to process.")
        return

    print(f"Processing item: {target_item['title']}")
    
    # 2. Fetch Content
    article_data = fetch_article_content(target_item['url'])
    if not article_data:
        print("Failed to fetch article content.")
        return

    # 3. Generate Script
    script_data = generate_bsd_script(article_data)
    if not script_data:
        print("Failed to generate script.")
        return
        
    script_file = "bsd_script.json"
    with open(script_file, "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=2, ensure_ascii=False)
        
    # 4. Generate Audio
    audio_folder = "bsd_output_audio"
    audio_paths = process_script(script_file, audio_folder)
    if not audio_paths:
        print("Failed to generate audio.")
        return

    # 5. Generate Thumbnail
    title = script_data.get("title", "Brain Science")
    # Truncate title if too long for prompt
    safe_title = title[:50]
    thumbnail_prompt = f"neuroscience, brain anatomy, scientific diagram, detailed illustration, {safe_title}, 4k"
    thumbnail_path = generate_thumbnail(thumbnail_prompt, output_filename="bsd_thumbnail.png")
    
    # 6. Create Video
    today_str = datetime.date.today().strftime("%Y%m%d")
    video_filename = f"bsd_video_{today_str}.mp4"
    if test_mode:
        video_filename = f"test_{video_filename}"
        
    video_path = get_unique_path(video_filename)
    
    final_video = create_podcast_video(
        thumbnail_path,
        audio_folder,
        video_path,
        script_file=script_file
    )
    
    if not final_video:
        print("Failed to create video.")
        return

    # 7. Upload
    print("\n=== Uploading ===")
    video_title = f"【脳科学辞典】{title} の解説"
    if test_mode:
        video_title = f"[TEST] {video_title}"
        
    description = f"脳科学辞典の「{title}」についての解説動画です。\n\n元記事:\n{target_item['url']}\n\n※この動画はAIによって自動生成されました。"
    
    try:
        video_id = upload_video(
            file_path=final_video,
            title=video_title,
            description=description,
            category_id="28", # Science & Technology
            keywords=["脳科学", "Neuroscience", "BSD", title],
            privacy_status="public" if not test_mode else "private"
        )
        print(f"Uploaded: https://youtu.be/{video_id}")
        
        # Update state only if successful (and not forced test?)
        # Actually update state if production run
        if not test_mode and not force_url:
            state['seen_urls'].append(target_item['url'])
            # Keep state size manageable
            if len(state['seen_urls']) > 1000:
                state['seen_urls'] = state['seen_urls'][-1000:]
            save_state(state)
            
    except Exception as e:
        print(f"Upload failed: {e}")

    return final_video

def run_once(test_mode=False):
    cleanup_temp_files()
    return generate_bsd_video(test_mode=test_mode)

def check_schedule_and_run(test_mode=False):
    """
    Checks if current time matches schedule (14:00 or 17:00).
    Expected to be called periodically.
    """
    # This might be used if run as a daemon, but server.js will handle scheduling.
    # This function acts as the entry point for server.js
    run_once(test_mode=test_mode)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Test mode")
    parser.add_argument("--once", action="store_true", help="Run once immediately")
    parser.add_argument("--url", type=str, help="Force process specific URL")
    
    args = parser.parse_args()
    
    if args.url:
        success = bool(generate_bsd_video(test_mode=args.test, force_url=args.url))
        sys.exit(0 if success else 1)
    elif args.once:
        success = bool(run_once(test_mode=args.test))
        sys.exit(0 if success else 1)
    else:
        # Default behavior: run once and exit with status.
        success = bool(run_once(test_mode=args.test))
        sys.exit(0 if success else 1)
