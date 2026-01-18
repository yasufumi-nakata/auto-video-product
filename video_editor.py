from moviepy import ImageClip, AudioFileClip, concatenate_audioclips, CompositeVideoClip, TextClip
import os
import glob
import json
import re


def create_podcast_video(image_path, audio_folder, output_filename="final_video.mp4", script_file=None):
    """
    指定された画像と、音声フォルダ内の全てのwavファイルを結合して動画を作成する。
    script_fileが指定されている場合は字幕を追加する。
    """
    print(f"Creating video from {image_path} and audio in {audio_folder}...")

    # 音声ファイルの取得とソート (000_...wav, 001_...wav の順)
    audio_files = sorted(glob.glob(os.path.join(audio_folder, "*.wav")))

    if not audio_files:
        print("No audio files found!")
        return None

    # 字幕情報を読み込み
    subtitles = []
    if script_file and os.path.exists(script_file):
        with open(script_file, "r", encoding="utf-8") as f:
            script_data = json.load(f)
            dialogues = script_data.get("dialogue", [])
            for i, d in enumerate(dialogues):
                subtitles.append({
                    "index": i,
                    "speaker": d["speaker"],
                    "text": d["text"]
                })

    # 音声クリップを作成し、各クリップの開始時刻を記録
    audio_clips = []
    clip_times = []  # (start_time, duration, index)
    current_time = 0.0

    for i, wav in enumerate(audio_files):
        clip = AudioFileClip(wav)
        audio_clips.append(clip)
        clip_times.append((current_time, clip.duration, i))
        current_time += clip.duration

    # 音声を結合
    final_audio = concatenate_audioclips(audio_clips)
    duration = final_audio.duration

    # 画像クリップを作成（音声と同じ長さにする）
    # サイズを1280x720に設定（YouTube推奨）
    image_clip = ImageClip(image_path).with_duration(duration).resized((1280, 720))

    # 字幕クリップを作成
    text_clips = []

    if subtitles and len(clip_times) == len(subtitles):
        print(f"Adding {len(subtitles)} subtitles...")

        for start_time, clip_duration, idx in clip_times:
            if idx < len(subtitles):
                sub = subtitles[idx]
                speaker = sub["speaker"]
                text = sub["text"]

                # 長いテキストは改行
                wrapped_text = wrap_text(text, max_chars=30)
                display_text = f"【{speaker}】\n{wrapped_text}"

                try:
                    # 字幕テキストクリップを作成
                    # macOS日本語フォントのパスを直接指定
                    font_path = '/System/Library/Fonts/Hiragino Sans GB.ttc'
                    txt_clip = TextClip(
                        text=display_text,
                        font_size=36,
                        color='white',
                        font=font_path,
                        stroke_color='black',
                        stroke_width=2,
                        method='caption',
                        size=(1200, None),
                        text_align='center'
                    )

                    # 位置と時間を設定
                    txt_clip = txt_clip.with_position(('center', 550))
                    txt_clip = txt_clip.with_start(start_time)
                    txt_clip = txt_clip.with_duration(clip_duration)

                    text_clips.append(txt_clip)
                except Exception as e:
                    print(f"Warning: Could not create subtitle {idx}: {e}")
    else:
        if subtitles:
            print(f"Warning: Subtitle count ({len(subtitles)}) != audio file count ({len(clip_times)})")

    # 動画を合成
    if text_clips:
        video = CompositeVideoClip([image_clip] + text_clips)
    else:
        video = image_clip

    video = video.with_audio(final_audio)

    # 書き出し
    # 字幕がある場合はfps=24が必要
    fps = 24 if text_clips else 1

    video.write_videofile(
        output_filename,
        fps=fps,
        codec='libx264',
        audio_codec='aac',
        threads=4
    )

    print(f"Video created successfully: {output_filename}")
    return output_filename


def wrap_text(text, max_chars=30):
    """
    テキストを指定文字数で改行する
    """
    lines = []
    current_line = ""

    for char in text:
        current_line += char
        if len(current_line) >= max_chars:
            lines.append(current_line)
            current_line = ""

    if current_line:
        lines.append(current_line)

    return "\n".join(lines)


def create_video_with_subtitles(image_path, audio_folder, script_file, output_filename="final_video.mp4"):
    """
    字幕付き動画を作成する便利関数
    """
    return create_podcast_video(image_path, audio_folder, output_filename, script_file)


if __name__ == "__main__":
    # Test
    if os.path.exists("thumbnail.png") and os.path.exists("output_audio"):
        if os.path.exists("script.json"):
            create_video_with_subtitles("thumbnail.png", "output_audio", "script.json", "test_video.mp4")
        else:
            create_podcast_video("thumbnail.png", "output_audio", "test_video.mp4")
