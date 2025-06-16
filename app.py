from flask import Flask, request, jsonify, send_file
import yt_dlp
import os
import tempfile
import uuid
import shutil
from pathlib import Path
import threading
import time
import requests
import random
import json

app = Flask(__name__)

# Configurações
TEMP_DIR = "/tmp/youtube_downloads"
MAX_FILE_AGE = 3600  # 1 hora

# Criar diretório temporário
os.makedirs(TEMP_DIR, exist_ok=True)

# Lista de proxies públicos (atualize regularmente)
PROXY_LIST = [
    'http://103.148.178.228:80',
    'http://20.206.106.192:80',
    'http://103.167.71.20:80',
    'http://103.148.178.228:80',
    'http://147.79.101.225:80',
    # Adicione mais conforme encontrar
]

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
        time.sleep(300)

cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

def test_proxy(proxy):
    """Testa se um proxy está funcionando"""
    try:
        response = requests.get(
            'http://httpbin.org/ip', 
            proxies={'http': proxy, 'https': proxy},
            timeout=10
        )
        if response.status_code == 200:
            return True
    except:
        pass
    return False

def get_working_proxy():
    """Encontra um proxy que funciona"""
    random.shuffle(PROXY_LIST)
    for proxy in PROXY_LIST:
        if test_proxy(proxy):
            return proxy
    return None

def download_with_external_service(url):
    """Usa serviço externo como fallback"""
    try:
        # Usando API do cobalt.tools (gratuita)
        api_url = "https://co.wuk.sh/api/json"
        
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        data = {
            'url': url,
            'vCodec': 'h264',
            'vQuality': '720',
            'aFormat': 'mp3',
            'filenamePattern': 'classic',
            'isAudioOnly': True
        }
        
        response = requests.post(api_url, json=data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 'success' and result.get('url'):
                return {
                    'success': True,
                    'download_url': result['url'],
                    'title': 'Audio Download',
                    'method': 'external_service'
                }
        
        return {'success': False, 'error': 'Serviço externo falhou'}
        
    except Exception as e:
        return {'success': False, 'error': f'Erro no serviço externo: {str(e)}'}

def download_audio_advanced(url, output_path):
    """Download com múltiplas estratégias incluindo proxies e serviços externos"""
    
    # Estratégia 1: Sem proxy com headers otimizados
    configs_direct = [
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
                    'player_client': ['android_music', 'android_creator'],
                    'skip': ['dash', 'hls']
                }
            },
            'http_headers': {
                'User-Agent': 'com.google.android.apps.youtube.music/5.16.51 (Linux; U; Android 11) gzip',
                'Accept-Language': 'en-US,en;q=0.9',
                'X-Forwarded-For': f'{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}',
                'CF-Connecting-IP': f'{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}'
            }
        }
    ]
    
    # Estratégia 2: Com proxy
    working_proxy = get_working_proxy()
    configs_proxy = []
    
    if working_proxy:
        configs_proxy = [
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
                'proxy': working_proxy,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept-Language': 'en-US,en;q=0.9',
                }
            }
        ]
    
    all_configs = configs_direct + configs_proxy
    
    # Tentar com yt-dlp primeiro
    for i, ydl_opts in enumerate(all_configs):
        try:
            method = "direto" if i < len(configs_direct) else "com proxy"
            print(f"Tentando yt-dlp {method}...")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'audio')
                duration = info.get('duration', 0)
                uploader = info.get('uploader', 'Unknown')
                
                ydl.download([url])
                
                return {
                    'title': title,
                    'duration': duration,
                    'uploader': uploader,
                    'method': f'yt-dlp_{method}',
                    'success': True
                }
        except Exception as e:
            print(f"yt-dlp {method} falhou: {e}")
            continue
    
    # Se yt-dlp falhou, tentar serviço externo
    print("Tentando serviço externo...")
    external_result = download_with_external_service(url)
    
    if external_result['success']:
        # Baixar o arquivo do serviço externo
        try:
            download_url = external_result['download_url']
            response = requests.get(download_url, timeout=60, stream=True)
            
            if response.status_code == 200:
                file_id = str(uuid.uuid4())
                audio_file = os.path.join(TEMP_DIR, f"{file_id}.mp3")
                
                with open(audio_file, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                return {
                    'title': external_result.get('title', 'Audio Download'),
                    'duration': 0,
                    'uploader': 'External Service',
                    'method': 'external_service',
                    'success': True,
                    'file_path': audio_file
                }
        except Exception as e:
            print(f"Erro ao baixar do serviço externo: {e}")
    
    # Se tudo falhou
    raise Exception("Todas as estratégias falharam")

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'service': 'YouTube Audio Downloader API',
        'version': '2.0.0',
        'status': 'Enhanced with proxy rotation and external services',
        'strategies': [
            'Direct connection with optimized headers',
            'Proxy rotation',
            'External download services',
            'IP spoofing headers'
        ],
        'endpoints': {
            'POST /download': 'Download audio with all strategies',
            'POST /download-external': 'Use only external services',
            'GET /health': 'API health check',
            'GET /proxy-status': 'Check proxy availability'
        }
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'version': '2.0.0',
        'proxy_available': get_working_proxy() is not None
    })

@app.route('/proxy-status', methods=['GET'])
def proxy_status():
    working_proxies = []
    for proxy in PROXY_LIST:
        if test_proxy(proxy):
            working_proxies.append(proxy)
    
    return jsonify({
        'total_proxies': len(PROXY_LIST),
        'working_proxies': len(working_proxies),
        'working_list': working_proxies
    })

@app.route('/download', methods=['POST'])
def download_video():
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type deve ser application/json'}), 400
        
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL é obrigatória'}), 400
        
        if 'youtube.com' not in url and 'youtu.be' not in url:
            return jsonify({'error': 'URL deve ser do YouTube'}), 400
        
        file_id = str(uuid.uuid4())
        temp_path = os.path.join(TEMP_DIR, f"{file_id}.%(ext)s")
        
        result = download_audio_advanced(url, temp_path)
        
        # Procurar arquivo gerado
        if result.get('file_path'):
            audio_file = result['file_path']
        else:
            possible_files = [
                os.path.join(TEMP_DIR, f"{file_id}.mp3"),
                os.path.join(TEMP_DIR, f"{file_id}.m4a"),
                os.path.join(TEMP_DIR, f"{file_id}.webm")
            ]
            
            audio_file = None
            for file_path in possible_files:
                if os.path.exists(file_path):
                    audio_file = file_path
                    break
        
        if not audio_file or not os.path.exists(audio_file):
            return jsonify({'error': 'Erro ao gerar arquivo de áudio'}), 500
        
        ext = os.path.splitext(audio_file)[1].lower()
        mime_types = {
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.webm': 'audio/webm'
        }
        
        return send_file(
            audio_file,
            as_attachment=True,
            download_name=f"{result['title']}.{ext[1:] if ext else 'mp3'}",
            mimetype=mime_types.get(ext, 'audio/mpeg')
        )
        
    except Exception as e:
        return jsonify({
            'error': 'Todas as estratégias falharam',
            'details': str(e),
            'suggestions': [
                'Tente novamente em alguns minutos',
                'Use um vídeo diferente',
                'Verifique se a URL está correta'
            ]
        }), 400

@app.route('/download-external', methods=['POST'])
def download_external_only():
    """Endpoint que usa apenas serviços externos"""
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL é obrigatória'}), 400
        
        result = download_with_external_service(url)
        
        if result['success']:
            return jsonify({
                'message': 'Use o link para download direto',
                'download_url': result['download_url'],
                'method': 'external_service'
            })
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
