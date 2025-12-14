import os
import time
import subprocess
import requests
import threading
import shutil
import signal
from flask import Flask, request, jsonify
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

app = Flask(__name__)

# --- কনফিগারেশন ---
current_process = None
observer = None
MAIN_CALLBACK_URL = ""
SECRET_TOKEN = ""
OUTPUT_DIR = "hls_output"
DOWNLOAD_DIR = "downloads"

# ফোল্ডার তৈরি
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- ফাইল আপলোডার ---
class FileUploader(FileSystemEventHandler):
    def on_created(self, event):
        self.process_event(event)
    
    def on_modified(self, event):
        self.process_event(event)
    
    def process_event(self, event):
        if event.is_directory: return
        filename = os.path.basename(event.src_path)
        
        if filename.endswith('.ts') or filename.endswith('.m3u8'):
            threading.Thread(target=self.upload_file, args=(event.src_path,)).start()

    def upload_file(self, filepath):
        time.sleep(1) # ফাইল সেভ হওয়ার জন্য অপেক্ষা
        if not os.path.exists(filepath): return
        
        try:
            with open(filepath, 'rb') as f:
                requests.post(
                    MAIN_CALLBACK_URL,
                    files={'file': f},
                    data={'token': SECRET_TOKEN},
                    timeout=15
                )
        except Exception as e:
            print(f"Upload Failed: {e}")

# --- ভিডিও ডাউনলোডার ---
def download_video(url):
    local_filename = os.path.join(DOWNLOAD_DIR, "source.mp4")
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
    
    # ১. ডাউনলোড
    local_video_path = download_video(url)
    if not local_video_path:
        return

    # ২. রেজুলেশন ও বিটরেট (লো-এন্ড সার্ভারের জন্য অপ্টিমাইজড)
    configs = {
        '1080p': ('1920x1080', '2500k'),
        '720p':  ('1280x720', '1500k'),
        '360p':  ('640x360', '500k')
    }
    res, bitrate = configs.get(quality, ('640x360', '500k'))
    output_file = os.path.join(OUTPUT_DIR, f"stream_{quality}.m3u8")

    # ৩. কমান্ড
    cmd = [
        'ffmpeg', 
        '-re',                  
        '-stream_loop', '-1',   
        '-i', local_video_path,
        '-s', res,              
        '-r', '24',             # Force 24 FPS (CPU বাঁচাতে)
        '-b:v', bitrate,        
        '-c:v', 'libx264',
        '-preset', 'ultrafast', # সর্বোচ্চ গতি
        '-tune', 'zerolatency', 
        '-sws_flags', 'bilinear', # ফাস্ট রিসাইজিং
        '-threads', '2',          # থ্রেড লিমিট
        '-g', '48',               # 2 sec Keyframe interval
        '-sc_threshold', '0',   
        '-hls_time', '5',       
        '-hls_list_size', '6',  
        '-hls_flags', 'delete_segments', 
        output_file
    ]
    
    print(f"Starting Stream: {quality}")
    current_process = subprocess.Popen(cmd)

# --- API ---
@app.route('/start-job', methods=['POST'])
def start_job():
    global MAIN_CALLBACK_URL, SECRET_TOKEN, observer, current_process
    
    data = request.json
    video_url = data.get('url')
    quality = data.get('quality')
    MAIN_CALLBACK_URL = data.get('callback_url')
    SECRET_TOKEN = data.get('token')
    
    # ক্লিনআপ
    if current_process:
        current_process.terminate()
        try: current_process.wait(timeout=5)
        except: current_process.kill()
        
    if observer:
        observer.stop()
        observer.join()

    if os.path.exists(OUTPUT_DIR): shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
        
    # কাজ শুরু
    observer = Observer()
    observer.schedule(FileUploader(), OUTPUT_DIR, recursive=False)
    observer.start()
    
    threading.Thread(target=run_ffmpeg, args=(video_url, quality)).start()
    
    return jsonify({"status": "started", "quality": quality})

@app.route('/')
def home():
    return "Render Worker Optimized is Ready"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
