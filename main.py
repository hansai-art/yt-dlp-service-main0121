from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from urllib.parse import urlparse
import logging
import subprocess
import json
import os
import uuid
import sys

logger = logging.getLogger("uvicorn.error")

app = FastAPI()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 下載目錄
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# 使用當前 Python 環境的 yt-dlp
YT_DLP_CMD = [sys.executable, "-m", "yt_dlp"]

class DownloadRequest(BaseModel):
    url: str

INDEX_PATH = Path(__file__).parent / "index.html"

@app.get("/")
async def root():
    """返回前端頁面"""
    if not INDEX_PATH.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(INDEX_PATH, media_type="text/html")

@app.post("/api/download")
async def download(req: DownloadRequest):
    """
    使用 yt-dlp 下載影片
    """
    url = (req.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="請輸入有效的URL")

    # 基本 URL 驗證
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="不支援的URL")

    try:
        # 先獲取影片資訊
        info_cmd = YT_DLP_CMD + [
            "--dump-json",
            "--no-download",
            "--no-warnings",
            url
        ]
        
        result = subprocess.run(
            info_cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or "無法獲取影片資訊"
            logger.error(f"yt-dlp info error: {error_msg}")
            raise HTTPException(status_code=400, detail=f"無法獲取影片資訊: {error_msg[:200]}")
        
        video_info = json.loads(result.stdout)
        title = video_info.get("title", "video")
        video_id = video_info.get("id", str(uuid.uuid4())[:8])
        
        # 安全的檔名
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
        if not safe_title:
            safe_title = "video"
        filename = f"{safe_title}_{video_id}.mp4"
        output_path = DOWNLOAD_DIR / filename
        
        # 下載影片 - 使用更穩定的格式選擇
        download_cmd = YT_DLP_CMD + [
            # 格式選擇：優先選擇有 URL 的格式，避免 SABR streaming 問題
            "-f", "bv*[protocol^=http]+ba[protocol^=http]/b[protocol^=http]/bv*+ba/b",
            "-o", str(output_path),
            "--no-playlist",
            "--no-warnings",
            "--merge-output-format", "mp4",
            # 使用 cookies 從瀏覽器（可選，增加成功率）
            # "--cookies-from-browser", "chrome",
            # 重試設定
            "--retries", "3",
            "--fragment-retries", "3",
            url
        ]
        
        result = subprocess.run(
            download_cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10分鐘超時
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or "下載失敗"
            logger.error(f"yt-dlp download error: {error_msg}")
            raise HTTPException(status_code=500, detail=f"下載失敗: {error_msg[:200]}")
        
        # 檢查檔案是否存在（yt-dlp 可能會使用不同的副檔名）
        if not output_path.exists():
            # 嘗試找到下載的檔案
            pattern = f"{safe_title}_{video_id}.*"
            matches = list(DOWNLOAD_DIR.glob(pattern))
            if matches:
                output_path = matches[0]
                filename = output_path.name
            else:
                # 檢查是否有任何新檔案
                all_files = list(DOWNLOAD_DIR.glob("*"))
                if all_files:
                    # 取最新的檔案
                    output_path = max(all_files, key=lambda p: p.stat().st_mtime)
                    filename = output_path.name
                else:
                    raise HTTPException(status_code=500, detail="下載完成但找不到檔案")
        
        return {
            "success": True,
            "downloadUrl": f"/api/file/{filename}",
            "filename": filename,
            "title": title,
            "source": "yt-dlp"
        }
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="下載超時，請稍後重試")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="無法解析影片資訊")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("未處理的錯誤")
        raise HTTPException(status_code=500, detail=f"發生錯誤: {str(e)}")

@app.get("/api/file/{filename}")
async def get_file(filename: str):
    """提供下載檔案"""
    # 防止路徑遍歷攻擊
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="無效的檔名")
    
    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="檔案不存在")
    
    # 根據副檔名決定 media type
    ext = file_path.suffix.lower()
    media_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type
    )

@app.get("/api/health")
async def health():
    """健康檢查"""
    # 檢查 yt-dlp 是否可用
    try:
        result = subprocess.run(
            YT_DLP_CMD + ["--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        yt_dlp_version = result.stdout.strip() if result.returncode == 0 else "unknown"
    except:
        yt_dlp_version = "not available"
    
    return {
        "status": "healthy",
        "api": "yt-dlp",
        "yt_dlp_version": yt_dlp_version,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    }

@app.get("/api/supported-platforms")
async def supported_platforms():
    """返回支援的平台列表"""
    return {
        "platforms": [
            "YouTube",
            "TikTok",
            "Instagram",
            "Twitter/X",
            "Reddit",
            "Pinterest",
            "Tumblr",
            "Vimeo",
            "Dailymotion",
            "Bilibili",
            "以及更多..."
        ],
        "note": "yt-dlp 支援 1000+ 個網站"
    }

@app.delete("/api/cleanup")
async def cleanup():
    """清理下載目錄"""
    try:
        for file in DOWNLOAD_DIR.iterdir():
            if file.is_file():
                file.unlink()
        return {"success": True, "message": "已清理下載目錄"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清理失敗: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)