import json
import os
import re
import threading
import webbrowser
from pathlib import Path

import imageio_ffmpeg
from flask import Flask, jsonify, make_response, render_template, request, send_file
from yt_dlp import YoutubeDL

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
DATA_DIR = BASE_DIR / "data"
STATS_FILE = DATA_DIR / "stats.json"
META_FILE = DATA_DIR / "files.json"

DOWNLOADS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

app = Flask(__name__)

jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()
stats_lock = threading.Lock()
meta_lock = threading.Lock()

DEFAULT_STATS = {"visitors": 0, "downloads": 0}


def load_stats() -> dict:
    if not STATS_FILE.exists():
        return dict(DEFAULT_STATS)
    try:
        data = json.loads(STATS_FILE.read_text(encoding="utf-8"))
        return {
            "visitors": int(data.get("visitors", 0)),
            "downloads": int(data.get("downloads", 0)),
        }
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return dict(DEFAULT_STATS)


def save_stats(stats: dict) -> None:
    STATS_FILE.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_stats() -> dict:
    with stats_lock:
        return load_stats()


def bump_stat(key: str) -> dict:
    with stats_lock:
        stats = load_stats()
        stats[key] = int(stats.get(key, 0)) + 1
        save_stats(stats)
        return dict(stats)


def load_meta() -> dict:
    if not META_FILE.exists():
        return {}
    try:
        data = json.loads(META_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {}


def save_meta(meta: dict) -> None:
    META_FILE.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def register_file(file_id: str, title: str, filename: str) -> None:
    with meta_lock:
        meta = load_meta()
        meta[file_id] = {
            "title": title,
            "filename": filename,
            "stored_as": f"{file_id}.mp3",
        }
        save_meta(meta)


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] or "audio"


def create_job(url: str) -> str:
    job_id = os.urandom(8).hex()
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "url": url,
            "title": "",
            "filename": "",
            "file_id": job_id,
            "error": "",
            "progress": 0,
        }
    return job_id


def update_job(job_id: str, **kwargs) -> None:
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kwargs)


def download_mp3(job_id: str, url: str) -> None:
    update_job(job_id, status="downloading", progress=5)
    work_dir = DOWNLOADS_DIR / f"_tmp_{job_id}"
    work_dir.mkdir(exist_ok=True)

    def progress_hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            if total > 0:
                pct = min(90, int(downloaded / total * 85) + 5)
                update_job(job_id, progress=pct, status="downloading")
        elif d.get("status") == "finished":
            update_job(job_id, progress=92, status="converting")

    outtmpl = str(work_dir / "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ffmpeg_location": FFMPEG_PATH,
        "progress_hooks": [progress_hook],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = sanitize_filename(info.get("title") or "audio")
            download_name = f"{title}.mp3"
            final_path = DOWNLOADS_DIR / f"{job_id}.mp3"

            produced = list(work_dir.glob("*.mp3"))
            if not produced:
                raise FileNotFoundError("لم يتم إنشاء ملف MP3")

            produced[0].replace(final_path)

            # cleanup temp folder
            for leftover in work_dir.iterdir():
                leftover.unlink(missing_ok=True)
            work_dir.rmdir()

            register_file(job_id, title, download_name)
            bump_stat("downloads")
            update_job(
                job_id,
                status="done",
                progress=100,
                title=title,
                filename=download_name,
                file_id=job_id,
            )
    except Exception as exc:
        # cleanup on failure
        if work_dir.exists():
            for leftover in work_dir.iterdir():
                leftover.unlink(missing_ok=True)
            try:
                work_dir.rmdir()
            except OSError:
                pass
        update_job(job_id, status="error", error=str(exc), progress=0)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/visit", methods=["POST"])
def api_visit():
    already = request.cookies.get("naghma_visited") == "1"
    if already:
        stats = get_stats()
        return jsonify({"ok": True, "counted": False, **stats})

    stats = bump_stat("visitors")
    resp = make_response(jsonify({"ok": True, "counted": True, **stats}))
    resp.set_cookie(
        "naghma_visited",
        "1",
        max_age=60 * 60 * 24 * 30,
        samesite="Lax",
        httponly=True,
    )
    return resp


@app.route("/api/stats")
def api_stats():
    return jsonify({"ok": True, **get_stats()})


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"ok": False, "error": "الرجاء إدخال رابط يوتيوب"}), 400

    if not re.search(r"(youtube\.com|youtu\.be)", url, re.I):
        return jsonify({"ok": False, "error": "الرابط يجب أن يكون من يوتيوب"}), 400

    job_id = create_job(url)
    thread = threading.Thread(target=download_mp3, args=(job_id, url), daemon=True)
    thread.start()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/status/<job_id>")
def api_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "المهمة غير موجودة"}), 404
    return jsonify({"ok": True, **job})


@app.route("/api/files")
def api_files():
    with meta_lock:
        meta = load_meta()

    files = []
    for path in sorted(DOWNLOADS_DIR.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True):
        file_id = path.stem
        info = meta.get(file_id, {})
        title = info.get("title") or file_id
        filename = info.get("filename") or f"{title}.mp3"
        files.append(
            {
                "id": file_id,
                "title": title,
                "name": filename,
                "size": path.stat().st_size,
                "mtime": int(path.stat().st_mtime),
            }
        )
    return jsonify({"ok": True, "files": files})


@app.route("/file/<file_id>")
def serve_file(file_id: str):
    if not re.fullmatch(r"[a-f0-9]{16}", file_id):
        return jsonify({"ok": False, "error": "معرف غير صالح"}), 400

    path = DOWNLOADS_DIR / f"{file_id}.mp3"
    if not path.exists():
        return jsonify({"ok": False, "error": "الملف غير موجود"}), 404

    with meta_lock:
        info = load_meta().get(file_id, {})

    download_name = info.get("filename") or f"{file_id}.mp3"
    return send_file(
        path,
        as_attachment=True,
        download_name=download_name,
        mimetype="audio/mpeg",
        conditional=True,
    )


def open_browser(url: str):
    webbrowser.open(url)


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    public_url = os.environ.get("PUBLIC_URL", f"http://127.0.0.1:{port}")
    open_local = os.environ.get("OPEN_BROWSER", "1") == "1"

    print(f"Downloads folder: {DOWNLOADS_DIR}")
    print(f"FFmpeg: {FFMPEG_PATH}")
    print(f"Server: http://{host}:{port}")
    print(f"Open: {public_url}")
    print("IMPORTANT: Do not host this app on Netlify (static only).")
    print("Use start.bat locally, or publish-online.bat for a public link.")

    if open_local and host in ("127.0.0.1", "localhost", "0.0.0.0"):
        threading.Timer(1.0, open_browser, args=(f"http://127.0.0.1:{port}",)).start()

    app.run(host=host, port=port, debug=False)
