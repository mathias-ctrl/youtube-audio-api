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
    # Lista de configurações para tentar (do mais simples ao mais avançado)
    configs = [
        # Configuração 1: Android Music client (mais eficaz contra bloqueios)
        {
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
            'extractor_args': {
                'youtube': {
                    'player_client': ['android_music', 'android'],
                    'skip': ['dash', 'hls']
                }
            },
            'http_headers': {
                'User-Agent': 'com.google.android.apps.youtube.music/5.16.51 (Linux; U; Android 11) gzip',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': '*/*'
            }
        },
        # Configuração 2: Android VR client
        {
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
            'extractor_args': {
                'youtube': {
                    'player_client': ['android_vr', 'android_creator'],
                    'skip': ['dash', 'hls']
                }
            },
            'http_headers': {
                'User-Agent': 'com.google.android.apps.youtube.vr.oculus/1.37.35 (Linux; U; Android 10; eureka-user 7.1.2) gzip',
            }
        },
        # Configuração 3: Mobile Firefox
        {
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
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'skip': ['dash', 'hls']
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Android 11; Mobile; rv:104.0) Gecko/104.0 Firefox/104.0',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            }
        },
        # Configuração 4: Fallback com qualidade menor
        {
            'format': 'worst[ext=mp4]/worst',
            'outtmpl': output_path,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['web'],
                }
            }
        },
        # Configuração 5: Último recurso - sem post-processing
        {
            'format': 'bestaudio[ext=m4a]/bestaudio/best[ext=m4a]/best',
            'outtmpl': output_path.replace('.%(ext)s', '.m4a'),
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }
    ]
    
    for i, ydl_opts in enumerate(configs):
        try:
            print(f"Tentando configuração {i+1}...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Obter informações do vídeo
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'audio')
                duration = info.get('duration', 0)
                uploader = info.get('uploader', 'Unknown')
                
                # Fazer o download
                ydl.download([url])
                
                print(f"Sucesso com configuração {i+1}")
                return {
                    'title': title,
                    'duration': duration,
                    'uploader': uploader,
                    'config_used': i+1
                }
        except Exception as e:
            print(f"Configuração {i+1} falhou: {e}")
            if i == len(configs) - 1:  # Última configuração
                raise e
            continue

@app.route('/', methods=['GET'])
def home():
    """Página inicial com documentação"""
    return jsonify({
        'service': 'YouTube Audio Downloader API',
        'version': '1.2.0',
        'status': 'Enhanced with multiple fallback configurations',
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
            'POST /info': {
                'description': 'Obter informações do vídeo sem baixar',
                'parameters': {
                    'url': 'URL do vídeo do YouTube (obrigatório)'
                }
            },
            'GET /health': 'Verificar status da API'
        },
        'usage': 'curl -X POST -H "Content-Type: application/json" -d \'{"url":"https://youtube.com/watch?v=ID"}\' http://your-domain/download',
        'notes': [
            'API usa múltiplas configurações de fallback para contornar bloqueios',
            'Alguns vídeos podem estar bloqueados dependendo da região/IP',
            'Vídeos mais antigos e populares tendem a funcionar melhor',
            'API tenta 5 configurações diferentes automaticamente'
        ],
        'tips': [
            'Use vídeos públicos sem restrições de idade',
            'Evite vídeos muito recentes (< 24h)',
            'URLs curtas (youtu.be) também funcionam'
        ]
    })

@app.route('/health', methods=['GET'])
def health():
    """Endpoint de health check"""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'version': '1.2.0',
        'temp_dir_exists': os.path.exists(TEMP_DIR),
        'temp_files_count': len(list(Path(TEMP_DIR).glob("*"))) if os.path.exists(TEMP_DIR) else 0
    })

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
        
        # Procurar pelo arquivo gerado (MP3 ou M4A)
        possible_files = [
            os.path.join(TEMP_DIR, f"{file_id}.mp3"),
            os.path.join(TEMP_DIR, f"{file_id}.m4a"),
            os.path.join(TEMP_DIR, f"{file_id}.webm"),
            os.path.join(TEMP_DIR, f"{file_id}.opus")
        ]
        
        audio_file = None
        for file_path in possible_files:
            if os.path.exists(file_path):
                audio_file = file_path
                break
        
        if not audio_file:
            return jsonify({'error': 'Erro ao gerar arquivo de áudio'}), 500
        
        # Determinar tipo MIME
        ext = os.path.splitext(audio_file)[1].lower()
        mime_types = {
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.webm': 'audio/webm',
            '.opus': 'audio/opus'
        }
        mimetype = mime_types.get(ext, 'audio/mpeg')
        
        # Retornar o arquivo
        return send_file(
            audio_file,
            as_attachment=True,
            download_name=f"{video_info['title']}.{ext[1:]}",
            mimetype=mimetype
        )
        
    except yt_dlp.DownloadError as e:
        error_msg = str(e)
        if "Sign in to confirm" in error_msg or "bot" in error_msg:
            return jsonify({
                'error': 'Vídeo temporariamente bloqueado pelo YouTube',
                'details': 'API tentou múltiplas configurações mas todas falharam',
                'suggestions': [
                    'Tente um vídeo diferente',
                    'Use vídeos mais antigos e populares',
                    'Evite vídeos com restrições de idade',
                    'Aguarde alguns minutos e tente novamente'
                ]
            }), 400
        return jsonify({'error': f'Erro no download: {error_msg}'}), 400
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
            'extractor_args': {
                'youtube': {
                    'player_client': ['android_music', 'android', 'web'],
                    'skip': ['dash', 'hls']
                }
            },
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            return jsonify({
                'title': info.get('title'),
                'uploader': info.get('uploader'),
                'duration': info.get('duration'),
                'duration_string': info.get('duration_string'),
                'view_count': info.get('view_count'),
                'upload_date': info.get('upload_date'),
                'description': info.get('description', '')[:300] + '...' if info.get('description') else None,
                'thumbnail': info.get('thumbnail'),
                'categories': info.get('categories', []),
                'tags': info.get('tags', [])[:10],  # Apenas primeiras 10 tags
                'availability': info.get('availability')
            })
            
    except Exception as e:
        return jsonify({'error': f'Erro ao obter informações: {str(e)}'}), 400

@app.route('/test', methods=['GET'])
def test_endpoint():
    """Endpoint de teste com URLs conhecidas"""
    test_urls = [
        'https://www.youtube.com/watch?v=dQw4w9WgXcQ',  # Rick Roll
        'https://www.youtube.com/watch?v=9bZkp7q19f0',  # PSY - Gangnam Style
        'https://www.youtube.com/watch?v=kJQP7kiw5Fk',  # Despacito
    ]
    
    return jsonify({
        'message': 'URLs de teste recomendadas',
        'test_urls': test_urls,
        'usage': 'Use essas URLs para testar a API - são vídeos populares que geralmente funcionam'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
