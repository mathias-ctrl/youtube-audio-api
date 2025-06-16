from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import tempfile
import uuid
import shutil
from pathlib import Path
import threading
import time

app = Flask(__name__)

# Configurações
TEMP_DIR = "/tmp/youtube_downloads"
MAX_FILE_AGE = 3600  # 1 hora

# Criar diretório temporário
os.makedirs(TEMP_DIR, exist_ok=True)

def cleanup_old_files():
    """Remove arquivos antigos periodicamente"""
    while True:
        try:
            current_time = time.time()
            for file_path in Path(TEMP_DIR).glob("*"):
                if current_time - file_path.stat().st_mtime > MAX_FILE_AGE:
                    file_path.unlink()
        except Exception as e:
            print(f"Erro na limpeza: {e}")
        time.sleep(300)  # Verificar a cada 5 minutos

# Iniciar thread de limpeza
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

def download_audio(url, output_path):
    """Baixa e converte o áudio do YouTube"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # Obter informações do vídeo
        info = ydl.extract_info(url, download=False)
        title = info.get('title', 'audio')
        duration = info.get('duration', 0)
        uploader = info.get('uploader', 'Unknown')
        
        # Fazer o download
        ydl.download([url])
        
        return {
            'title': title,
            'duration': duration,
            'uploader': uploader
        }

@app.route('/', methods=['GET'])
def home():
    """Página inicial com documentação"""
    return jsonify({
        'service': 'YouTube Audio Downloader API',
        'version': '1.0.0',
        'endpoints': {
            'POST /download': {
                'description': 'Baixar áudio de um vídeo do YouTube',
                'parameters': {
                    'url': 'URL do vídeo do YouTube (obrigatório)'
                },
                'example': {
                    'url': 'https://www.youtube.com/watch?v=VIDEO_ID'
                }
            },
            'GET /health': 'Verificar status da API'
        },
        'usage': 'curl -X POST -H "Content-Type: application/json" -d \'{"url":"https://youtube.com/watch?v=ID"}\' http://your-domain/download'
    })

@app.route('/health', methods=['GET'])
def health():
    """Endpoint de health check"""
    return jsonify({'status': 'healthy', 'timestamp': time.time()})

@app.route('/download', methods=['POST'])
def download_video():
    """Endpoint principal para download de áudio"""
    try:
        # Validar JSON
        if not request.is_json:
            return jsonify({'error': 'Content-Type deve ser application/json'}), 400
        
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL é obrigatória'}), 400
        
        # Validar URL
        if 'youtube.com' not in url and 'youtu.be' not in url:
            return jsonify({'error': 'URL deve ser do YouTube'}), 400
        
        # Gerar ID único para o arquivo
        file_id = str(uuid.uuid4())
        temp_path = os.path.join(TEMP_DIR, f"{file_id}.%(ext)s")
        
        # Fazer o download
        video_info = download_audio(url, temp_path)
        
        # Encontrar o arquivo MP3 gerado
        mp3_file = os.path.join(TEMP_DIR, f"{file_id}.mp3")
        
        if not os.path.exists(mp3_file):
            return jsonify({'error': 'Erro ao converter áudio'}), 500
        
        # Retornar o arquivo
        return send_file(
            mp3_file,
            as_attachment=True,
            download_name=f"{video_info['title']}.mp3",
            mimetype='audio/mpeg'
        )
        
    except yt_dlp.DownloadError as e:
        return jsonify({'error': f'Erro no download: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@app.route('/info', methods=['POST'])
def get_video_info():
    """Obter apenas informações do vídeo sem baixar"""
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type deve ser application/json'}), 400
        
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL é obrigatória'}), 400
        
        # Configurar yt-dlp apenas para extrair info
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            return jsonify({
                'title': info.get('title'),
                'uploader': info.get('uploader'),
                'duration': info.get('duration'),
                'view_count': info.get('view_count'),
                'upload_date': info.get('upload_date'),
                'description': info.get('description', '')[:200] + '...' if info.get('description') else None
            })
            
    except Exception as e:
        return jsonify({'error': f'Erro ao obter informações: {str(e)}'}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
