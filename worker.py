import os
import time
import subprocess
import requests
import threading
import shutil
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# --- কনফিগারেশন ---
current_process = None
OUTPUT_DIR = "hls_output"
DOWNLOAD_DIR = "downloads"

# ফোল্ডার তৈরি
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- নতুন রাউট: ফাইল সার্ভ করা (Proxy Mode এর জন্য জরুরি) ---
@app.route(f'/{OUTPUT_DIR}/<path:filename>')
def serve_hls_files(filename):
    """
    এই রাউটটি Main VPS-কে ফাইল অ্যাক্সেস করতে দেয়।
    URL হবে: https://worker-url.com/hls_output/stream.m3u8
    """
    # ক্যাশ কন্ট্রোল হেডার যোগ করা যাতে ব্রাউজার লেটেস্ট ফাইল পায়
    response = send_from_directory(OUTPUT_DIR, filename)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

# --- ভিডিও ডাউনলোডার ---
def download_video(url):
    local_filename = os.path.join(DOWNLOAD_DIR, "source.mp4")
    # আগের ফাইল থাকলে ডিলিট করা
    if os.path.exists(local_filename):
        os.remove(local_filename)
        
    print(f"Downloading video from {url}...")
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print("Download complete.")
        return local_filename
    except Exception as e:
        print(f"Download Error: {e}")
        return None

# --- FFmpeg রানার (Optimized) ---
def run_ffmpeg(url, quality):
    global current_process
    
    # ১. ভিডিও ডাউনলোড করা
    local_video_path = download_video(url)
    if not local_video_path:
        print("Video download failed.")
        return

    # ২. রেজুলেশন ও বিটরেট কনফিগারেশন
    configs = {
        '1080p': ('1920x1080', '2500k'),
        '720p':  ('1280x720', '1500k'),
        '360p':  ('640x360', '500k')
    }
    res, bitrate = configs.get(quality, ('640x360', '500k'))
    
    output_file = os.path.join(OUTPUT_DIR, f"stream_{quality}.m3u8")

    # ৩. FFmpeg কমান্ড (CPU বাঁচানোর জন্য অপ্টিমাইজড)
    cmd = [
        'ffmpeg', 
        '-re',                  
        '-stream_loop', '-1',   
        '-i', local_video_path,
        '-s', res,              
        '-r', '24',             # 24 FPS ফিক্সড (CPU লোড কমাবে)
        '-b:v', bitrate,        
        '-c:v', 'libx264',
        '-preset', 'ultrafast', # দ্রুততম এনকোডিং
        '-tune', 'zerolatency', 
        '-sws_flags', 'bilinear', 
        '-threads', '2',          
        '-g', '48',               
        '-sc_threshold', '0',   
        '-hls_time', '5',       
        '-hls_list_size', '6',  
        '-hls_flags', 'delete_segments', 
        output_file
    ]
    
    print(f"Starting Stream: {quality}")
    current_process = subprocess.Popen(cmd)

# --- API: জব শুরু করা ---
@app.route('/start-job', methods=['POST'])
def start_job():
    global current_process
    
    data = request.json
    video_url = data.get('url')
    quality = data.get('quality')
    
    # আগের প্রসেস বন্ধ করা
    if current_process:
        current_process.terminate()
        try: current_process.wait(timeout=5)
        except: current_process.kill()

    # আগের ফাইল ক্লিন করা
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
    
    # নতুন থ্রেডে FFmpeg শুরু করা
    threading.Thread(target=run_ffmpeg, args=(video_url, quality)).start()
    
    return jsonify({"status": "started", "mode": "proxy_serving", "quality": quality})

@app.route('/')
def home():
    return "Render Worker (Proxy Mode) is Ready"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
