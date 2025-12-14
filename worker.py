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

# --- ফাইল আপলোডার ক্লাস ---
class FileUploader(FileSystemEventHandler):
    def on_created(self, event):
        self.process_event(event)
            
    def on_modified(self, event):
        self.process_event(event)
    
    def process_event(self, event):
        # ফোল্ডার বা টেম্প ফাইল ইগনোর করা
        if event.is_directory: return
        filename = os.path.basename(event.src_path)
        
        if filename.endswith('.ts') or filename.endswith('.m3u8'):
            # আলাদা থ্রেডে আপলোড করা যাতে মূল প্রসেস স্লো না হয়
            threading.Thread(target=self.upload_file, args=(event.src_path,)).start()

    def upload_file(self, filepath):
        # ফাইলটি রাইট হওয়ার জন্য ১ সেকেন্ড অপেক্ষা
        time.sleep(1)
        
        if not os.path.exists(filepath): return
        
        filename = os.path.basename(filepath)
        try:
            with open(filepath, 'rb') as f:
                # মেইন সার্ভারে পাঠানো
                requests.post(
                    MAIN_CALLBACK_URL,
                    files={'file': f},
                    data={'token': SECRET_TOKEN},
                    timeout=5
                )
        except Exception as e:
            print(f"Upload Failed [{filename}]: {e}")

# --- FFmpeg রানার ---
def run_ffmpeg(url, quality):
    global current_process
    
    # রেজুলেশন কনফিগারেশন
    configs = {
        '1080p': ('1920x1080', '4500k'),
        '720p':  ('1280x720', '2500k'),
        '360p':  ('640x360', '800k')
    }
    # ডিফল্ট 360p যদি কিছু না মেলে
    res, bitrate = configs.get(quality, ('640x360', '800k'))
    
    # ফাইলের নাম আলাদা করা (stream_720p.m3u8)
    output_file = os.path.join(OUTPUT_DIR, f"stream_{quality}.m3u8")

    # FFmpeg কমান্ড (রিয়েল-টাইম লুপ এবং সিঙ্ক ফিক্সড)
    cmd = [
        'ffmpeg', 
        '-re',                  # রিয়েল টাইম রিডিং
        '-stream_loop', '-1',   # অসীম লুপ
        '-i', url,
        '-s', res,              # রেজুলেশন
        '-b:v', bitrate,        # বিটরেট
        '-c:v', 'libx264',
        '-preset', 'veryfast',  # সিপিইউ বাঁচাতে ফাস্ট প্রিসেট
        '-g', '150',            # Keyframe Interval (Sync এর জন্য জরুরি)
        '-sc_threshold', '0',   # সিন ডিটেকশন বন্ধ
        '-hls_time', '5',       # ৫ সেকেন্ডের সেগমেন্ট
        '-hls_list_size', '6',  # প্লেলিস্টে ৬টি ফাইল
        '-hls_flags', 'delete_segments', # পুরানো ফাইল ডিলিট
        output_file
    ]
    
    # প্রসেস শুরু
    current_process = subprocess.Popen(cmd)
    print(f"Started streaming {quality}...")

# --- API Endpoint ---
@app.route('/start-job', methods=['POST'])
def start_job():
    global MAIN_CALLBACK_URL, SECRET_TOKEN, observer, current_process
    
    data = request.json
    video_url = data.get('url')
    quality = data.get('quality')
    MAIN_CALLBACK_URL = data.get('callback_url')
    SECRET_TOKEN = data.get('token')
    
    # ১. আগের প্রসেস এবং ওয়াচার বন্ধ করা
    if current_process:
        current_process.terminate()
        current_process.wait()
        
    if observer:
        observer.stop()
        observer.join()

    # ২. ফোল্ডার ক্লিন করা
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
        
    # ৩. ফাইল ওয়াচার চালু করা
    observer = Observer()
    observer.schedule(FileUploader(), OUTPUT_DIR, recursive=False)
    observer.start()
    
    # ৪. নতুন FFmpeg জব শুরু করা
    threading.Thread(target=run_ffmpeg, args=(video_url, quality)).start()
    
    return jsonify({"status": "started", "quality": quality})

@app.route('/')
def home():
    return "Render Worker Node is Active with Docker & FFmpeg"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
