# Autocut - AI Video Clipper 🎬🤖

This project is a powerful Python script that automates the entire process of creating short, engaging video clips from long-form YouTube videos. It uses AI to intelligently analyze content, identify the best moments, and generate ready-to-post clips with dynamic subtitles.

The script is designed to be a flexible pipeline, capable of handling various types of content—from lectures and podcasts to live concerts and animated shows—using a sophisticated system of AI prompts and data analysis.

## Core Features ✨

-   **Intelligent Content Analysis**: Leverages the Google Gemini Pro AI model to analyze video transcripts and identify the most compelling segments for short clips.
-   **Precision Cutting with Timestamps**: Uses Whisper for highly accurate, timestamped transcriptions, ensuring clips start and end exactly where they should.
-   **Dynamic Subtitle Generation**: Automatically creates and burns dynamic, word-by-word style subtitles onto the final video clips using MoviePy.
-   **Smart Show/Concert Analysis**: If a video description contains a timestamped setlist (e.g., a live concert), the script bypasses AI analysis and cuts the video directly based on the provided tracklist for perfect accuracy.
-   **Customizable AI Prompts**: Easily define different "personalities" for the AI editor via external `.txt` prompt files. Create presets for podcasts, comedy shows, music analysis, etc.
-   **User-Directed AI Context**: Guide the AI's choices by providing additional context via command-line arguments (e.g., `"focus on funny moments"`).
-   **Resilient & Cache-Based Workflow**: The script saves its progress at every major step (download, transcription, AI analysis). If it's interrupted, you can simply run it again, and it will resume from where it left off.
-   **Optimized Performance**:
    -   Downloads videos at a maximum of 1080p to save space and processing time.
    -   Automatically attempts to use an NVIDIA GPU (CUDA for Whisper, NVENC for video encoding) for massive speed improvements, with a graceful fallback to a CPU-optimized process.

## How it Works: The Pipeline ⚙️

1.  **Fetch & Analyze Metadata**: The script fetches the video's title and description from YouTube.
2.  **Decision Point**:
    -   **If a "show" prompt is used and a timestamped setlist is found in the description (or a manual setlist file is provided)**, it enters **Direct Mode**. It skips AI analysis entirely and generates clip metadata directly from the setlist.
    -   **Otherwise**, it enters **AI Analysis Mode**.
3.  **AI Analysis Mode**:
    -   The full video (up to 1080p) is downloaded using `yt-dlp`.
    -   The audio is extracted.
    -   The audio is transcribed into detailed, timestamped segments using `Whisper`.
    -   The timestamped transcript, along with a selected prompt and any user-provided context, is sent to the Gemini AI.
    -   The AI returns a list of the best moments with precise start and end times.
4.  **Clip Generation**:
    -   The original video is cut into clips based on the generated metadata.
    -   If enabled, dynamic subtitles are generated and overlaid onto each clip.
    -   The final clips are saved in a dedicated folder: `output/[video_id]/`.
5.  **Cleanup**: Temporary files (full video, audio, transcript) are automatically deleted upon successful completion.

## Setup & Installation 🛠️

#### Prerequisites

1.  **Python 3.8+**: Make sure Python is installed on your system.
2.  **Git**: Required to install some Python packages directly from GitHub.
3.  **FFmpeg**: This is a critical dependency for `moviepy` to process video files.
    -   **Windows**: Download from [FFmpeg's website](https://ffmpeg.org/download.html) and add it to your system's PATH.
    -   **macOS**: `brew install ffmpeg`
    -   **Linux (Ubuntu/Debian)**: `sudo apt update && sudo apt install ffmpeg`
4.  **(Optional, for GPU Acceleration)** **NVIDIA GPU & CUDA**:
    -   An NVIDIA graphics card.
    -   The latest NVIDIA drivers.
    -   The [NVIDIA CUDA Toolkit](https://developer.nvidia.com/cuda-toolkit) (version 11.8 or newer recommended).

#### Installation Steps

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd projeto-cortes-ia
    ```

2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    ```

3.  **Activate the environment:**
    -   **Windows (PowerShell):** `.\venv\Scripts\Activate.ps1`
    -   **macOS/Linux:** `source venv/bin/activate`

4.  **Install dependencies:**
    -   **For CPU-only users:**
        ```bash
        pip install -r requirements.txt
        ```
    -   **For NVIDIA GPU users (HIGHLY RECOMMENDED):**
        First, install the correct version of PyTorch with CUDA support. Go to the [PyTorch website](https://pytorch.org/get-started/locally/) to get the correct command for your CUDA version. Then, install the other requirements.
        ```bash
        # Example for CUDA 11.8
        pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
        pip install -r requirements.txt
        ```

5.  **Set up API Keys:**
    -   Create a `.env` file in the root directory by copying the example:
        ```bash
        # Windows
        copy .env.example .env
        # macOS/Linux
        cp .env.example .env
        ```
    -   Open the `.env` file and add your Google AI Studio API key:
        ```
        GOOGLE_API_KEY="your_google_api_key_here"
        ```

6.  **Create Prompt Files:**
    -   Create a folder named `prompts` in the root directory.
    -   Inside this folder, create `.txt` files for each AI persona you want. The name of the file (e.g., `show.txt`) will be the name of the prompt you use in the command line.
    -   See the `prompts/` directory in this repository for examples.

## Usage 🚀

The script is controlled via the command line.

#### Basic Syntax
```bash
python main.py "YOUTUBE_URL" [OPTIONS]
```

#### Examples

**1. Standard Analysis (for a podcast or lecture):**
```bash
python main.py "https://www.youtube.com/watch?v=some-podcast-id"
```

**2. Analyzing a Live Concert:**
This uses the `show.txt` prompt. It will first check the description for a timestamped setlist before falling back to AI analysis.
```bash
python main.py "https://www.youtube.com/watch?v=live-concert-id" --prompt show
```

**3. Providing a Manual Setlist:**
If the setlist is in the comments, copy it to a file (e.g., `setlist.txt`) and pass it to the script.
```bash
python main.py "URL" --prompt show --setlist "path/to/setlist.txt"
```

**4. Guiding the AI with Context:**
Analyze a comedy show, telling the AI to focus on a specific character.
```bash
python main.py "URL" --prompt comedy --context "Focus on jokes made by the character Peter Griffin."
```

**5. Generating Clips Without Subtitles:**
For a faster process, you can disable subtitle generation.
```bash
python main.py "URL" --no-subtitles
```

#### All Command-Line Arguments

-   `url` (Required): The full URL of the YouTube video.
-   `--prompt`: The prompt preset to use (corresponds to a filename in the `prompts/` folder). Default: `padrao`.
-   `--context`: A string of text to provide additional context to the AI.
-   `--setlist`: Path to a local `.txt` file containing a manually provided setlist.
-   `--no-subtitles`: If present, disables the subtitle generation process.
