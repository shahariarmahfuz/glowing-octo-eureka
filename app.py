from flask import Flask, request, redirect, url_for, send_from_directory, render_template_string
import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp4', 'mkv', 'avi', 'mov'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

HTML_PAGE = """
<!doctype html>
<title>Video Upload</title>
<h2>Upload Video</h2>
<form method=post enctype=multipart/form-data>
  <input type=file name=video>
  <input type=submit value=Upload>
</form>

{% if filename %}
<hr>
<p><b>Upload Complete!</b></p>
<p>▶ View Link: <a href="{{ view_url }}" target="_blank">{{ view_url }}</a></p>
<p>⬇ Download Link: <a href="{{ download_url }}">{{ download_url }}</a></p>
{% endif %}
"""

@app.route('/', methods=['GET', 'POST'])
def upload_video():
    filename = None
    view_url = None
    download_url = None

    if request.method == 'POST':
        file = request.files.get('video')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            view_url = url_for('view_video', filename=filename, _external=True)
            download_url = url_for('download_video', filename=filename, _external=True)

    return render_template_string(
        HTML_PAGE,
        filename=filename,
        view_url=view_url,
        download_url=download_url
    )

@app.route('/view/<filename>')
def view_video(filename):
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=False
    )

@app.route('/download/<filename>')
def download_video(filename):
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        filename,
        as_attachment=True
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
