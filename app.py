from flask import Flask, request, jsonify, send_from_directory, render_template
import os
import math

app = Flask(__name__)

UPLOAD_DIR = "uploads"
CHUNK_DIR = "temp_chunks"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CHUNK_DIR, exist_ok=True)

@app.route("/")
def index():
    return render_template("upload.html")

@app.route("/upload_chunk", methods=["POST"])
def upload_chunk():
    file = request.files["chunk"]
    filename = request.form["filename"]
    chunk_index = int(request.form["chunk_index"])

    chunk_path = os.path.join(CHUNK_DIR, f"{filename}.part{chunk_index}")
    file.save(chunk_path)

    return jsonify({"status": "chunk uploaded"})

@app.route("/merge_chunks", methods=["POST"])
def merge_chunks():
    filename = request.json["filename"]
    total_chunks = int(request.json["total_chunks"])

    final_path = os.path.join(UPLOAD_DIR, filename)

    with open(final_path, "wb") as outfile:
        for i in range(total_chunks):
            part_path = os.path.join(CHUNK_DIR, f"{filename}.part{i}")
            with open(part_path, "rb") as infile:
                outfile.write(infile.read())
            os.remove(part_path)

    return jsonify({
        "view": f"/view/{filename}",
        "download": f"/download/{filename}"
    })

@app.route("/view/<filename>")
def view_video(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)

@app.route("/download/<filename>")
def download_video(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
