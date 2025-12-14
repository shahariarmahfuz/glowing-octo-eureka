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

# --- গ্লোবাল ভেরিয়েবল ---
current_process = None
observer = None
MAIN_CALLBACK_URL = ""
SECRET_TOKEN = ""
OUTPUT_DIR = "hls_output"
DOWNLOAD_DIR = "downloads"  # ডাউনলোড ফোল্ডার

# ফোল্ডার তৈরি
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- ফাইল আপলোডার ক্লাস ---
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
        time.sleep(1) # ফাইল রাইট হওয়ার জন্য অপেক্ষা
        
        if not os.path.exists(filepath): return
        
        filename = os.path.basename(filepath)
        try:
            with open(filepath, 'rb') as f:
                requests.post(
                    MAIN_CALLBACK_URL,
                    files={'file': f},
                    data={'token': SECRET_TOKEN},
                    timeout=10 # টাইমআউট বাড়ানো হয়েছে
                )
        except Exception as e:
            print(f"Upload Failed [{filename}]: {e}")

# --- ভিডিও ডাউনলোড ফাংশন ---
def download_video(url):
    local_filename = os.path.join(DOWNLOAD_DIR, "source_video.mp4")
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
        print(f"Download error: {e}")
        return None

# --- FFmpeg রানার ---
def run_ffmpeg(url, quality):
    global current_process
    
    # ১. আগে ভিডিও ডাউনলোড করা (এরর ফিক্স)
    local_video_path = download_video(url)
    if not local_video_path:
        print("Could not download video, aborting.")
        return

    # রেজুলেশন কনফিগারেশন
    configs = {
        '1080p': ('1920x1080', '4000k'), # বিটরেট একটু কমানো হয়েছে ক্র্যাশ এড়াতে
        '720p':  ('1280x720', '2000k'),
        '360p':  ('640x360', '600k')
    }
    res, bitrate = configs.get(quality, ('640x360', '600k'))
    
    output_file = os.path.join(OUTPUT_DIR, f"stream_{quality}.m3u8")

    # FFmpeg কমান্ড (Ultrafast + Local File)
    cmd = [
        'ffmpeg', 
        '-re',                  
        '-stream_loop', '-1',   
        '-i', local_video_path, # এখন লোকাল ফাইল ব্যবহার হবে
        '-s', res,              
        '-b:v', bitrate,        
        '-c:v', 'libx264',
        '-preset', 'ultrafast', # স্পিড বাড়ানোর জন্য (Crucial fix)
        '-tune', 'zerolatency', # লাইভ স্ট্রিমিং অপ্টিমাইজেশন
        '-g', '150',            
        '-sc_threshold', '0',   
        '-hls_time', '5',       
        '-hls_list_size', '6',  
        '-hls_flags', 'delete_segments', 
        output_file
    ]
    
    print(f"Starting FFmpeg for {quality} using {local_video_path}...")
    current_process = subprocess.Popen(cmd)

# --- API Endpoint ---
@app.route('/start-job', methods=['POST'])
def start_job():
    global MAIN_CALLBACK_URL, SECRET_TOKEN, observer, current_process
    
    data = request.json
    video_url = data.get('url')
    quality = data.get('quality')
    MAIN_CALLBACK_URL = data.get('callback_url')
    SECRET_TOKEN = data.get('token')
    
    # ১. ক্লিনআপ
    if current_process:
        current_process.terminate()
        try:
            current_process.wait(timeout=5)
        except:
            current_process.kill()
        
    if observer:
        observer.stop()
        observer.join()

    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
        
    # ২. ওয়াচার চালু
    observer = Observer()
    observer.schedule(FileUploader(), OUTPUT_DIR, recursive=False)
    observer.start()
    
    # ৩. কাজ শুরু (থ্রেডে)
    threading.Thread(target=run_ffmpeg, args=(video_url, quality)).start()
    
    return jsonify({"status": "downloading_and_starting", "quality": quality})

@app.route('/')
def home():
    return "Render Worker (v2 - Local Download) is Ready"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
