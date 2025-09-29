import os
import json
import yt_dlp
from moviepy.editor import VideoFileClip
import whisper
import google.generativeai as genai
from dotenv import load_dotenv

# --- 1. CONFIGURAÇÃO INICIAL ---

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("A chave de API do Google não foi encontrada. Verifique seu arquivo .env")

genai.configure(api_key=GOOGLE_API_KEY)

# --- 2. DEFINIÇÃO DAS FUNÇÕES ---

def download_video(url, output_path="video.mp4"):
    """Baixa um vídeo de uma URL usando yt-dlp."""
    print(f"Baixando vídeo de: {url}...")
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'merge_output_format': 'mp4',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print(f"Vídeo salvo em: {output_path}")
        return output_path
    except Exception as e:
        print(f"Erro no download: {e}")
        return None

def extract_audio(video_path, audio_path="audio.mp3"):
    """Extrai o áudio de um arquivo de vídeo usando MoviePy."""
    print(f"Extraindo áudio de: {video_path}...")
    try:
        with VideoFileClip(video_path) as video:
            video.audio.write_audiofile(audio_path)
        print(f"Áudio salvo em: {audio_path}")
        return audio_path
    except Exception as e:
        print(f"Erro ao extrair áudio: {e}")
        return None

def transcribe_audio(audio_path):
    """Transcreve um arquivo de áudio usando o Whisper."""
    print("Iniciando transcrição com Whisper (isso pode levar um tempo)...")
    try:
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, language="pt")
        print("Transcrição concluída.")
        return result['text']
    except Exception as e:
        print(f"Erro na transcrição: {e}")
        return None

def get_clips_from_ai(transcription, video_duration):
    """Envia a transcrição para o Gemini e pede sugestões de cortes em formato JSON."""
    print("Enviando transcrição para a IA para análise de cortes...")
    
    # ALTERADO: Modelo de IA para 'gemini-pro' para garantir compatibilidade.
    model = genai.GenerativeModel('gemini-2.5-flash')

    prompt = f"""
    Analise a seguinte transcrição de um vídeo que tem {video_duration:.2f} segundos de duração.
    Seu objetivo é identificar os 3 trechos mais impactantes e que funcionariam bem como vídeos curtos (Reels, Shorts, TikTok).

    Para cada trecho, determine o tempo de início e fim em segundos.
    
    A sua resposta DEVE ser um objeto JSON válido, contendo uma única chave "cortes".
    O valor dessa chave deve ser uma lista de objetos, onde cada objeto representa um corte e contém as seguintes chaves:
    - "titulo": Um título curto e chamativo para o clipe.
    - "inicio_s": O tempo de início do corte em segundos (apenas o número).
    - "fim_s": O tempo de fim do corte em segundos (apenas o número).

    Exemplo de formato de resposta:
    {{
      "cortes": [
        {{
          "titulo": "A Dica Mais Importante",
          "inicio_s": 35.5,
          "fim_s": 62.0
        }}
      ]
    }}

    Transcrição:
    ---
    {transcription}
    ---
    """

    try:
        response = model.generate_content(prompt)
        json_response_text = response.text.strip().replace("```json", "").replace("```", "")
        
        print("Análise da IA recebida.")
        return json.loads(json_response_text)
    except Exception as e:
        print(f"Erro ao analisar com a IA ou ao decodificar o JSON: {e}")
        return None

def create_video_clips(video_path, clips_data):
    """Cria os arquivos de vídeo para cada corte sugerido usando MoviePy."""
    print("Iniciando a criação dos clipes de vídeo...")
    try:
        with VideoFileClip(video_path) as video:
            for i, clip_info in enumerate(clips_data['cortes']):
                # Garante que o título seja seguro para nomes de arquivo
                titulo = "".join(c for c in clip_info['titulo'] if c.isalnum() or c in (' ', '_')).rstrip().replace(" ", "_").lower()
                inicio = float(clip_info['inicio_s'])
                fim = float(clip_info['fim_s'])
                
                output_filename = f"corte_{i+1}_{titulo}.mp4"
                print(f"-> Criando clipe: {output_filename} de {inicio}s a {fim}s")
                
                new_clip = video.subclip(inicio, fim)
                new_clip.write_videofile(output_filename, codec="libx264", audio_codec="aac")
        print("Criação de clipes finalizada com sucesso!")
    except Exception as e:
        print(f"Erro ao criar os clipes de vídeo: {e}")

# --- 3. EXECUÇÃO PRINCIPAL ---

if __name__ == "__main__":
    video_url = "https://www.youtube.com/watch?v=gjIJXrneXD0" # VIDEO AQUI
    video_filename = "video_baixado.mp4"
    
    # Etapa 1: Download
    video_file = download_video(video_url, video_filename)
    
    if video_file:
        transcription_text = None
        # NOVO: Lógica para usar a transcrição em cache
        cache_filename = video_file.replace('.mp4', '_transcription.txt')
        
        if os.path.exists(cache_filename):
            print(f"Cache encontrado! Carregando transcrição de '{cache_filename}'")
            with open(cache_filename, 'r', encoding='utf-8') as f:
                transcription_text = f.read()
        else:
            print("Nenhum cache de transcrição encontrado. Iniciando novo processo.")
            # Etapa 2: Extração de Áudio
            audio_file = extract_audio(video_file)
            if audio_file:
                # Etapa 3: Transcrição
                transcription_text = transcribe_audio(audio_file)
                if transcription_text:
                    # NOVO: Salva a transcrição em um arquivo de cache para uso futuro
                    print(f"Salvando transcrição em cache: '{cache_filename}'")
                    with open(cache_filename, 'w', encoding='utf-8') as f:
                        f.write(transcription_text)

        # Continua o processo se tivermos a transcrição (do cache ou nova)
        if transcription_text:
            # Etapa 4: Análise com IA
            with VideoFileClip(video_file) as v:
                duration = v.duration
            
            suggested_clips = get_clips_from_ai(transcription_text, duration)
            
            if suggested_clips:
                # Etapa 5: Criação dos Cortes
                create_video_clips(video_file, suggested_clips)