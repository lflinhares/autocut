import os
import json
import re
import argparse
import hashlib
import yt_dlp
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
import whisper
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("Google API key not found.")
genai.configure(api_key=GOOGLE_API_KEY)

def load_prompts_from_folder(folder_path="prompts"):
    if not os.path.isdir(folder_path):
        print(f"WARNING: Prompts folder '{folder_path}' not found.")
        return {}
    presets = {}
    for filename in os.listdir(folder_path):
        if filename.endswith(".txt"):
            preset_name = os.path.splitext(filename)[0]
            with open(os.path.join(folder_path, filename), 'r', encoding='utf-8') as f:
                presets[preset_name] = f.read()
    return presets

def get_video_id(url):
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    return match.group(1) if match else None

def sanitize_filename(name):
    return "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).rstrip()

def timestamp_to_seconds(ts_str):
    parts = list(map(int, ts_str.split(':')))
    seconds = 0
    if len(parts) == 3:
        seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        seconds = parts[0] * 60 + parts[1]
    return seconds

def parse_timestamps_from_description(description):
    """Searches for timestamps in various common formats and extracts the tracklist."""
    tracklist = []
    
    pattern_end = re.compile(r'^(.*?)\s*-\s*((\d{1,2}:)?\d{1,2}:\d{2})$', re.MULTILINE)
    matches_end = pattern_end.findall(description)
    for match in matches_end:
        title, timestamp_str, _ = match
        cleaned_title = re.sub(r'^\d+\s*[\.\-]?\s*', '', title).strip()
        start_seconds = timestamp_to_seconds(timestamp_str)
        tracklist.append({
            "start_seconds": start_seconds,
            "title": cleaned_title
        })

    pattern_start = re.compile(r'^((\d{1,2}:)?\d{1,2}:\d{2})\s*[\-]?\s*(.*)', re.MULTILINE)
    matches_start = pattern_start.findall(description)
    for match in matches_start:
        timestamp_str, _, title = match
        if not any(t['title'] in title for t in tracklist):
            start_seconds = timestamp_to_seconds(timestamp_str)
            tracklist.append({
                "start_seconds": start_seconds,
                "title": title.strip()
            })

    if not tracklist:
        return None

    tracklist.sort(key=lambda x: x['start_seconds'])
    
    return tracklist if len(tracklist) >= 2 else None

def download_video(url, output_path):
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            video_title = info_dict.get('title', 'Unknown Title')
            video_description = info_dict.get('description', '')
        if os.path.exists(output_path):
            print(f"Video file already exists. Skipping download.")
            return output_path, video_title, video_description
        print(f"Downloading video from: {url} (max quality: 1080p)...")
        ydl_opts = {'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]',
                    'outtmpl': output_path, 'merge_output_format': 'mp4'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print(f"Video saved to: {output_path}")
        return output_path, video_title, video_description
    except Exception as e:
        print(f"Download error: {e}")
        return None, None, None

def extract_audio(video_path, audio_path):
    if os.path.exists(audio_path):
        print(f"Audio file already exists. Skipping extraction.")
        return audio_path
    print(f"Extracting audio from: {video_path}...")
    try:
        with VideoFileClip(video_path) as video:
            video.audio.write_audiofile(audio_path, logger=None)
        print(f"Audio saved to: {audio_path}")
        return audio_path
    except Exception as e:
        print(f"Error extracting audio: {e}")
        return None

def get_transcription_segments(audio_path, transcription_path):
    if os.path.exists(transcription_path):
        print(f"Loading transcription segments from cache.")
        with open(transcription_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    print("Starting detailed transcription with Whisper...")
    try:
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, language="en")
        segments = result['segments']
        print("Saving transcription segments to cache.")
        with open(transcription_path, 'w', encoding='utf-8') as f:
            json.dump(segments, f, indent=4, ensure_ascii=False)
        return segments
    except Exception as e:
        print(f"Transcription error: {e}")
        return None

def get_or_create_metadata_from_ai(segments, metadata_path, original_title, url, prompt_text, additional_context=None):
    if os.path.exists(metadata_path):
        print(f"Loading metadata from cache: '{metadata_path}'")
        with open(metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    print("Formatting transcription for the AI...")
    formatted_transcription = ""
    for segment in segments:
        formatted_transcription += f"[{segment['start']:.2f}s - {segment['end']:.2f}s] {segment['text']}\n"
    additional_context_str = f"\n\nAdditional Context (User-provided):\n---\n{additional_context}\n---" if additional_context else ""
    print("Sending transcription to the AI for analysis...")
    model = genai.GenerativeModel('gemini-1.5-pro-latest')
    try:
        full_prompt = f"{prompt_text}{additional_context_str}\n\nFull Transcription:\n---\n{formatted_transcription}\n---"
        response = model.generate_content(full_prompt)
        json_response_text = response.text.strip().replace("```json", "").replace("```", "")
        ai_data = json.loads(json_response_text)
        metadata = {"original_url": url, "original_title": original_title, "clips": ai_data.get("clips", [])}
        print(f"Saving metadata to '{metadata_path}'...")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=4, ensure_ascii=False)
        return metadata
    except Exception as e:
        print(f"Error analyzing with AI or decoding JSON: {e}")
        return None

def create_video_clips(video_path, metadata, project_folder, with_subtitles, segments=None):
    action_str = "with subtitles" if with_subtitles else "without subtitles"
    print(f"Starting the creation of video clips {action_str}...")
    if not metadata or 'clips' not in metadata:
        print("Invalid metadata or no clips to process.")
        return False
    END_BUFFER_SECONDS = 1.0
    try:
        with VideoFileClip(video_path) as video:
            for i, clip_info in enumerate(metadata['clips']):
                sanitized_title = sanitize_filename(clip_info['title'])
                output_filename = os.path.join(project_folder, f"clip_{i+1}_{sanitized_title}.mp4")
                if os.path.exists(output_filename):
                    print(f"Clip '{output_filename}' already exists. Skipping.")
                    continue
                start_s = float(clip_info['start_s'])
                end_s = float(clip_info['end_s'])
                end_buffered = min(video.duration, end_s + (END_BUFFER_SECONDS if with_subtitles else 0.0))
                print(f"-> Creating clip: {output_filename} from {start_s:.2f}s to {end_buffered:.2f}s")
                main_clip = video.subclip(start_s, end_buffered)
                final_clip = main_clip
                if with_subtitles and segments:
                    subtitle_clips = []
                    clip_segments = [s for s in segments if s['start'] >= start_s and s['end'] <= end_buffered]
                    for segment in clip_segments:
                        start_time = segment['start'] - start_s
                        end_time = segment['end'] - start_s
                        text = segment['text'].strip().upper()
                        txt_clip = TextClip(text, fontsize=70, color='white', font='Arial-Bold',
                                            stroke_color='black', stroke_width=3,
                                            size=(main_clip.w * 0.8, None), method='caption')
                        txt_clip = txt_clip.set_pos(('center', 'center')).set_start(start_time).set_duration(end_time - start_time)
                        subtitle_clips.append(txt_clip)
                    final_clip = CompositeVideoClip([main_clip] + subtitle_clips)
                final_clip.write_videofile(output_filename, codec="libx264", audio_codec="aac", logger=None)
        print(f"Clip creation {action_str} finished successfully!")
        return True
    except Exception as e:
        print(f"Error creating video clips: {e}")
        return False

def cleanup_temp_files(files_to_delete):
    print("\nCleaning up temporary files...")
    for file_path in files_to_delete:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f" - Deleted: {file_path}")
        except Exception as e:
            print(f"Error deleting {file_path}: {e}")

if __name__ == "__main__":
    PROMPT_PRESETS = load_prompts_from_folder()
    parser = argparse.ArgumentParser(description="Automates the creation of video clips using AI.")
    parser.add_argument("url", type=str, help="The URL of the YouTube video to process.")
    parser.add_argument("--prompt", type=str, default="default", choices=PROMPT_PRESETS.keys(), help="The prompt preset to use.")
    parser.add_argument("--context", type=str, help="Additional text to provide more context to the AI prompt.")
    parser.add_argument("--no-subtitles", action="store_true", help="Generate clips without subtitles.")
    parser.add_argument("--setlist", type=str, help="Path to a .txt file with the manual setlist (format: HH:MM:SS Title).")
    args = parser.parse_args()
    
    video_url = args.url
    prompt_key = args.prompt
    additional_context = args.context
    selected_prompt = PROMPT_PRESETS.get(prompt_key)
    if not selected_prompt:
        raise SystemExit(f"ERROR: Prompt preset '{prompt_key}' not found in the 'prompts' folder.")
    generate_with_subtitles = not args.no_subtitles
    
    MAIN_OUTPUT_FOLDER = "output"
    os.makedirs(MAIN_OUTPUT_FOLDER, exist_ok=True)
    video_id = get_video_id(video_url)
    if not video_id:
        raise ValueError("Invalid video URL or could not extract ID.")
    project_folder = os.path.join(MAIN_OUTPUT_FOLDER, video_id)
    os.makedirs(project_folder, exist_ok=True)
    print(f"--- Processing video ID: {video_id} ---")
    
    video_path = os.path.join(project_folder, "downloaded_video.mp4")
    audio_path = os.path.join(project_folder, "audio.mp3")
    transcription_path = os.path.join(project_folder, "transcription_segments.json")
    context_hash = "_" + hashlib.md5(additional_context.encode()).hexdigest()[:8] if additional_context else ""
    metadata_mode = "direct" if prompt_key == "show" else f"ai_{prompt_key}{context_hash}"
    metadata_filename = f"metadata_{metadata_mode}.json"
    metadata_path = os.path.join(project_folder, metadata_filename)

    run_successful = False
    try:
        video_file, video_title, video_description = download_video(video_url, video_path)
        if not video_file: raise Exception("Download failed.")

        metadata = None
        if os.path.exists(metadata_path):
            print(f"Loading metadata from cache: '{metadata_path}'")
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        else:
            tracklist = None
            if args.setlist:
                print(f">>> Reading setlist from manual file: {args.setlist}")
                try:
                    with open(args.setlist, 'r', encoding='utf-8') as f:
                        manual_description = f.read()
                    tracklist = parse_timestamps_from_description(manual_description)
                    if not tracklist:
                        print("WARNING: Setlist file provided, but no timestamps found in the expected format.")
                except FileNotFoundError:
                    print(f"ERROR: Setlist file not found at '{args.setlist}'.")
            
            elif prompt_key == "show":
                tracklist = parse_timestamps_from_description(video_description)

            if tracklist:
                print(">>> Tracklist found in description! Using Direct Clipping Mode.")
                clips = []
                for i in range(len(tracklist)):
                    start_time = tracklist[i]['start_seconds']
                    end_time = tracklist[i+1]['start_seconds'] if i + 1 < len(tracklist) else start_time + 180 # 3 min fallback
                    clips.append({
                        "title": tracklist[i]['title'],
                        "description": f"Clip of the song {tracklist[i]['title']} from the show {video_title}.",
                        "start_s": start_time,
                        "end_s": end_time
                    })
                metadata = {"original_url": video_url, "original_title": video_title, "clips": clips}
                print(f"Saving metadata (Direct Mode) to '{metadata_path}'...")
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=4, ensure_ascii=False)
            else:
                if prompt_key == "show":
                    print(">>> No tracklist found. Using AI Analysis Mode for the show.")
                else:
                    print(">>> Using AI Analysis Mode.")
                
                audio_file = extract_audio(video_file, audio_path)
                if not audio_file: raise Exception("Audio extraction failed.")
                transcription_segments = get_transcription_segments(audio_file, transcription_path)
                if not transcription_segments: raise Exception("Transcription failed.")
                metadata = get_or_create_metadata_from_ai(transcription_segments, metadata_path, video_title, video_url, selected_prompt, additional_context)

        if not metadata: raise Exception("Failed to generate metadata.")

        transcription_segments_for_subs = None
        if generate_with_subtitles:
            audio_file = extract_audio(video_file, audio_path)
            if audio_file:
                transcription_segments_for_subs = get_transcription_segments(audio_file, transcription_path)

        success = create_video_clips(video_file, metadata, project_folder, with_subtitles=generate_with_subtitles, segments=transcription_segments_for_subs)
        if not success: raise Exception("Clip creation failed.")

        run_successful = True

    except Exception as e:
        print(f"\nERROR: The process was interrupted. {e}")
        print("You can run the script again to continue from where it left off.")

    finally:
        if run_successful:
            files_to_clean = [video_path, audio_path, transcription_path]
            cleanup_temp_files(files_to_clean)
            print("\n--- Process completed successfully! ---")