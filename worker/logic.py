import os
import json
import re
import argparse
import hashlib
import yt_dlp
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

def download_video(url, cache_folder, output_filename="downloaded_video.mp4"):
    """
    Downloads a video using yt-dlp, forcing all files into the cache_folder.
    Returns the full path to the final video file.
    """
    full_output_path = os.path.join(cache_folder, output_filename)
    
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            video_title = info_dict.get('title', 'Unknown Title')
            video_description = info_dict.get('description', '')

        if os.path.exists(full_output_path):
            print(f"Video file already exists in cache. Skipping download.")
            return full_output_path, video_title, video_description

        print(f"Downloading video from: {url} into cache: {cache_folder}")
        
        ydl_opts = {
            'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]',
            'paths': {'home': cache_folder},
            'outtmpl': output_filename,
            'merge_output_format': 'mp4'
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        print(f"Video saved to cache: {full_output_path}")
        return full_output_path, video_title, video_description
        
    except Exception as e:
        print(f"Download error: {e}")
        return None, None, None

def extract_audio(video_path, audio_path):
    
    from moviepy import VideoFileClip
    
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
    import whisper
    
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
    model = genai.GenerativeModel('gemini-2.5-pro')
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
    from moviepy import VideoFileClip, TextClip, CompositeVideoClip
    
    created_clips = []
    action_str = "with subtitles" if with_subtitles else "without subtitles"
    print(f"Starting the creation of video clips {action_str}...")
    if not metadata or 'clips' not in metadata:
        print("Invalid metadata or no clips to process.")
        return []
    END_BUFFER_SECONDS = 1.0
    try:
        with VideoFileClip(video_path) as video:
            for i, clip_info in enumerate(metadata['clips']):
                sanitized_title = sanitize_filename(clip_info['title'])
                output_filename = os.path.join(project_folder, f"clip_{i+1}_{sanitized_title}.mp4")
                
                if os.path.exists(output_filename):
                    print(f"Clip '{output_filename}' already exists. Skipping.")
                    created_clips.append(output_filename)
                    continue
                    
                start_s = float(clip_info['start_s'])
                end_s = float(clip_info['end_s'])
                end_buffered = min(video.duration, end_s + (END_BUFFER_SECONDS if with_subtitles else 0.0))
                
                print(f"-> Creating clip: {output_filename} from {start_s:.2f}s to {end_buffered:.2f}s")
                main_clip = video.subclipped(start_s, end_buffered)
                
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
                created_clips.append(output_filename) # Add successful clip to the list

        print(f"Clip creation {action_str} finished successfully!")
        return created_clips
    except Exception as e:
        print(f"Error creating video clips: {e}")
        import traceback
        traceback.print_exc()
        return []

def cleanup_temp_files(files_to_delete):
    print("\nCleaning up temporary files...")
    for file_path in files_to_delete:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f" - Deleted: {file_path}")
        except Exception as e:
            print(f"Error deleting {file_path}: {e}")

def run_processing_pipeline(job_id: int, url: str):
    """
    This function contains the main logic from your original script,
    now with a proper caching strategy.
    """
    print(f"PIPELINE [Job {job_id}]: Starting process for URL: {url}")
    
    video_id = get_video_id(url)
    if not video_id:
        raise ValueError("Could not extract video ID from URL.")
    
    cache_folder = os.path.join("output", video_id, "_cache")
    os.makedirs(cache_folder, exist_ok=True)
    
    job_output_folder = os.path.join("output", video_id, str(job_id))
    os.makedirs(job_output_folder, exist_ok=True)

    audio_path = os.path.join(cache_folder, "audio.mp3")
    transcription_path = os.path.join(cache_folder, "transcription_segments.json")
    
    metadata_path = os.path.join(job_output_folder, "metadata.json")

    PROMPT_PRESETS = load_prompts_from_folder()
    selected_prompt = PROMPT_PRESETS.get("default")
    if not selected_prompt: raise ValueError("Default prompt not found.")
    generate_with_subtitles = False

    video_file, video_title, _ = download_video(url, cache_folder)
    if not video_file: raise Exception("Download failed.")

    audio_file = extract_audio(video_file, audio_path)
    if not audio_file: raise Exception("Audio extraction failed.")

    transcription_segments = get_transcription_segments(audio_file, transcription_path)
    if not transcription_segments: raise Exception("Transcription failed.")

    metadata = get_or_create_metadata_from_ai(
        transcription_segments, metadata_path, video_title, url, selected_prompt
    )
    if not metadata: raise Exception("Failed to generate AI metadata.")

    final_clip_paths = create_video_clips(
        video_file, metadata, job_output_folder, 
        with_subtitles=generate_with_subtitles, 
        segments=transcription_segments
    )
    if not final_clip_paths:
        raise Exception("Clip creation process failed.")

    print(f"PIPELINE [Job {job_id}]: Process completed successfully.")
    return final_clip_paths