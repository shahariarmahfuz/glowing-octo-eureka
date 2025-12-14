# হালকা পাইথন ভার্সন ব্যবহার করছি
FROM python:3.10-slim

# সিস্টেম আপডেট এবং FFmpeg ইন্সটল
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# কাজের ফোল্ডার সেট করা
WORKDIR /app

# লাইব্রেরি ইন্সটল
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# কোড কপি করা
COPY worker.py .

# অ্যাপ রান করা (Gunicorn দিয়ে)
CMD ["gunicorn", "worker:app", "-b", "0.0.0.0:10000"]
