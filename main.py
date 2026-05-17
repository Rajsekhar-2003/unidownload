import os
import re
import uuid
import shutil
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

import yt_dlp

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# =========================================================
# DIRECTORIES
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

DOWNLOAD_DIR = BASE_DIR / "downloads"
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"

DOWNLOAD_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATE_DIR.mkdir(exist_ok=True)

# =========================================================
# CLEANUP TASK
# =========================================================

async def cleanup_old_files():
    """
    Delete downloaded files older than 3 hours
    """
    while True:
        try:
            now = datetime.now()

            for file in DOWNLOAD_DIR.iterdir():
                if file.is_file():
                    age = now - datetime.fromtimestamp(file.stat().st_mtime)

                    if age > timedelta(hours=3):
                        file.unlink(missing_ok=True)
                        logger.info(f"Deleted old file: {file.name}")

        except Exception as e:
            logger.error(f"Cleanup error: {e}")

        await asyncio.sleep(3600)

# =========================================================
# FASTAPI LIFESPAN
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    task = asyncio.create_task(cleanup_old_files())

    yield

    task.cancel()

# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI(
    title="Video Downloader API",
    description="Download YouTube, Instagram, Facebook videos",
    version="2.0.0",
    lifespan=lifespan
)

# =========================================================
# MIDDLEWARE
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

# =========================================================
# STATIC + TEMPLATES
# =========================================================

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static"
)

templates = Jinja2Templates(
    directory=str(TEMPLATE_DIR)
)

# =========================================================
# SUPPORTED PLATFORMS
# =========================================================

SUPPORTED_PLATFORMS = {
    "youtube": r"(youtube\.com|youtu\.be)",
    "instagram": r"(instagram\.com|instagr\.am)",
    "facebook": r"(facebook\.com|fb\.watch)"
}

# =========================================================
# QUALITY MAP
# =========================================================

QUALITY_MAP = {
    "320p": "bestvideo[height<=360]+bestaudio/best",  # Added 320p
    "720p": "bestvideo[height<=720]+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best",
    "2k": "bestvideo[height<=1440]+bestaudio/best"  # Changed from 1440p to 2k
}

# =========================================================
# HELPERS
# =========================================================

def detect_platform(url: str):

    for platform, pattern in SUPPORTED_PLATFORMS.items():

        if re.search(pattern, url, re.IGNORECASE):
            return platform

    return "unknown"


def sanitize_filename(filename: str):

    return re.sub(r'[<>:"/\\|?*]', '', filename)


def get_format_string(quality: str, download_type: str):

    if download_type == "mp3":
        return "bestaudio/best"

    return QUALITY_MAP.get(quality, QUALITY_MAP["720p"])


def get_ydlp_opts(
    format_string: str,
    output_path: Path,
    download_type: str
):

    opts = {
        "format": format_string,
        "outtmpl": str(output_path),
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "ignoreerrors": True,
        "no_check_certificate": True,
    }

    # MP3 conversion
    if download_type == "mp3":

        opts.update({
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        })

    return opts

# =========================================================
# ROUTES
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        return templates.TemplateResponse(request, "index.html")
    except Exception as e:
        logger.error(f"Template error: {e}")
        return HTMLResponse(
            content=f"<h1>Error loading page: {str(e)}</h1>",
            status_code=500
        )

# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
async def health():

    return {
        "status": "ok",
        "time": datetime.now().isoformat()
    }

# =========================================================
# VIDEO INFO
# =========================================================

@app.get("/api/info")
async def get_video_info(url: str):

    try:

        platform = detect_platform(url)

        if platform == "unknown":
            raise HTTPException(
                status_code=400,
                detail="Unsupported URL"
            )

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(url, download=False)

            formats = info.get("formats", [])

            qualities = set()

            for fmt in formats:

                height = fmt.get("height")

                if height and height <= 1440:
                    qualities.add(f"{height}p")

            # Add default qualities if none found
            if not qualities:
                qualities = {"360p", "720p", "1080p"}

            sorted_qualities = sorted(
                list(qualities),
                key=lambda x: int(x.replace("p", ""))
            )

            return JSONResponse({
                "success": True,
                "title": info.get("title"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "platform": platform,
                "qualities": sorted_qualities
            })

    except Exception as e:

        logger.error(f"Info error: {e}")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# =========================================================
# DOWNLOAD VIDEO
# =========================================================

@app.get("/api/download")
async def download_video(
    url: str,
    quality: str = "720p",
    type: str = "mp4"
):

    file_path = None  # Track file path for cleanup

    try:

        platform = detect_platform(url)

        if platform == "unknown":
            raise HTTPException(
                status_code=400,
                detail="Unsupported platform"
            )

        if type not in ["mp4", "mp3"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid type"
            )

        unique_id = str(uuid.uuid4())[:8]

        output_template = DOWNLOAD_DIR / f"{unique_id}_%(title)s.%(ext)s"

        format_string = get_format_string(quality, type)

        ydl_opts = get_ydlp_opts(
            format_string,
            output_template,
            type
        )

        logger.info(f"Downloading: {url}")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(url, download=True)

            downloaded_file = ydl.prepare_filename(info)

            # Correct extension
            if type == "mp3":
                downloaded_file = str(
                    Path(downloaded_file).with_suffix(".mp3")
                )

            file_path = Path(downloaded_file)

            # Find file if not found
            if not file_path.exists():

                files = list(DOWNLOAD_DIR.glob(f"{unique_id}*"))

                if not files:
                    raise HTTPException(
                        status_code=500,
                        detail="Download failed"
                    )

                file_path = files[0]

            title = sanitize_filename(
                info.get("title", "video")
            )

            final_filename = f"{title}_{quality}.{type}"

            # Create a delayed deletion function
            def delete_file():
                try:
                    if file_path and file_path.exists():
                        file_path.unlink()
                        logger.info(f"Deleted file: {file_path}")
                except Exception as e:
                    logger.error(f"Error deleting file: {e}")

            # Use background task with delay
            background_tasks = BackgroundTasks()
            background_tasks.add_task(delete_file)

            logger.info(f"Download completed: {file_path}")

            return FileResponse(
                path=file_path,
                filename=final_filename,
                media_type=(
                    "video/mp4"
                    if type == "mp4"
                    else "audio/mpeg"
                ),
                background=background_tasks
            )

    except Exception as e:

        logger.error(f"Download error: {e}")
        
        # Clean up partial download if exists
        if file_path and file_path.exists():
            try:
                file_path.unlink()
            except:
                pass

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )