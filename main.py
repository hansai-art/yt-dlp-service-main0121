from fastapi import FastAPI, HTTPException  
from fastapi.middleware.cors import CORSMiddleware  
import yt_dlp  
import os  
import tempfile  
app = FastAPI()  
# 添加 CORS 支持  
app.add_middleware(  
    CORSMiddleware,  
    allow_origins=["*"],  
    allow_credentials=True,  
    allow_methods=["*"],  
    allow_headers=["*"],  
)  
def get_ydl_opts(output_path=None):  
    """獲取 yt-dlp 配置，支持 YouTube 認證"""  
    if output_path is None:  
        output_path = tempfile.gettempdir()  
      
    return {  
        'format': 'best',  
        'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),  
        'quiet': False,  
        'no_warnings': False,  
        'socket_timeout': 30,  
        'http_headers': {  
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',  
            'Accept-Language': 'en-US,en;q=0.9',  
        },  
        'extractor_args': {  
            'youtube': {  
                'lang': ['en'],  
            }  
        },  
        'skip_unavailable_fragments': True,  
        'fragment_retries': 3,  
        'retries': 3,  
        'socket_timeout': 30,  
    }  
@app.get("/")  
async def root():  
    return {"message": "yt-dlp API Server", "status": "running"}  
@app.get("/api/health")  
async def health():  
    return {"status": "ok"}  
@app.post("/api/download")  
async def download_video(url: str):  
    """下載視頻"""  
    if not url:  
        raise HTTPException(status_code=400, detail="URL is required")  
      
    try:  
        temp_dir = tempfile.mkdtemp()  
        ydl_opts = get_ydl_opts(temp_dir)  
          
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  
            print(f"Downloading: {url}")  
            info = ydl.extract_info(url, download=True)  
            filename = ydl.prepare_filename(info)  
              
            return {  
                "status": "success",  
                "title": info.get('title', 'Unknown'),  
                "duration": info.get('duration', 0),  
                "uploader": info.get('uploader', 'Unknown'),  
                "filename": os.path.basename(filename)  
            }  
      
    except yt_dlp.utils.DownloadError as e:  
        raise HTTPException(status_code=400, detail=f"Download error: {str(e)}")  
    except Exception as e:  
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")  
@app.post("/api/info")  
async def get_video_info(url: str):  
    """獲取視頻信息（不下載）"""  
    if not url:  
        raise HTTPException(status_code=400, detail="URL is required")  
      
    try:  
        ydl_opts = get_ydl_opts()  
          
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:  
            print(f"Getting info for: {url}")  
            info = ydl.extract_info(url, download=False)  
              
            return {  
                "status": "success",  
                "title": info.get('title', 'Unknown'),  
                "duration": info.get('duration', 0),  
                "uploader": info.get('uploader', 'Unknown'),  
                "upload_date": info.get('upload_date', 'Unknown'),  
                "view_count": info.get('view_count', 0),  
                "description": info.get('description', '')[:200],  
                "formats": len(info.get('formats', []))  
            }  
      
    except yt_dlp.utils.DownloadError as e:  
        raise HTTPException(status_code=400, detail=f"Video unavailable: {str(e)}")  
    except Exception as e:  
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")  
if __name__ == "__main__":  
    import uvicorn  
    uvicorn.run(app, host="0.0.0.0", port=8080)  
