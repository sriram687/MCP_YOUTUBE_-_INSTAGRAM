import os
import time
import tempfile
import json
import logging
import shutil
import uuid
from typing import List, Optional
from pathlib import Path
import uvicorn
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
import moviepy.editor as mp
from fastmcp import FastMCP
from pyngrok import ngrok

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="MCP Video Upload Server",
    description="Upload videos to YouTube Shorts and Instagram Reels via MCP",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize MCP
mcp = FastMCP("Video Upload MCP Server")

# --- NGROK SETUP for Instagram ---
# Create a temporary directory to store videos for public access
TEMP_DIR = Path("temp_videos_public")
TEMP_DIR.mkdir(exist_ok=True)
# Mount this directory so it can be accessed from the web
app.mount("/static", StaticFiles(directory=TEMP_DIR), name="static")

try:
    NGROK_TOKEN = os.getenv("NGROK_AUTHTOKEN")
    if not NGROK_TOKEN:
        raise ValueError("NGROK_AUTHTOKEN not found in .env file. Please get one from dashboard.ngrok.com")
    ngrok.set_auth_token(NGROK_TOKEN)
    public_url = ngrok.connect(8000).public_url
    logger.info(f"✅ ngrok tunnel is active at: {public_url}")
except Exception as e:
    public_url = None
    logger.error(f"❌ Could not start ngrok. Error: {e}")
    logger.error("❌ Instagram uploads will fail. Please ensure ngrok is installed and your authtoken is correct.")

class YouTubeUploader:
    def __init__(self):
        self.client_id = os.getenv("YOUTUBE_CLIENT_ID")
        self.client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
        self.access_token = os.getenv("YOUTUBE_ACCESS_TOKEN")
        self.refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
        
        if not all([self.client_id, self.client_secret, self.access_token, self.refresh_token]):
            raise ValueError("Missing YouTube OAuth credentials in environment variables")

    def _get_credentials(self):
        """Get valid YouTube API credentials, refreshing if necessary."""
        creds = Credentials(
            token=self.access_token,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret
        )
        
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Update the access token in memory (you might want to persist this)
            self.access_token = creds.token
            
        return creds

    def upload_video(self, video_path: str, title: str, description: str, tags: List[str]) -> dict:
        """Upload video to YouTube and return video details."""
        try:
            # Get video duration to determine if it's a Short
            with mp.VideoFileClip(video_path) as video:
                duration = video.duration
            
            is_short = duration < 60
            
            # Build YouTube service
            credentials = self._get_credentials()
            youtube = build("youtube", "v3", credentials=credentials)
            
            # Prepare video metadata
            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "categoryId": "22"  # People & Blogs category
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False
                }
            }
            
            # Add Shorts-specific metadata if applicable
            if is_short:
                body["snippet"]["title"] = f"#Shorts {title}"
                if "#Shorts" not in body["snippet"]["description"]:
                    body["snippet"]["description"] = f"#Shorts\n{description}"
            
            # Upload the video
            media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/*")
            
            request = youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = request.execute()
            
            video_id = response["id"]
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            
            return {
                "success": True,
                "video_id": video_id,
                "watch_url": watch_url,
                "is_short": is_short,
                "duration": duration
            }
            
        except HttpError as e:
            logger.error(f"YouTube upload error: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"YouTube API error: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error during YouTube upload: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Upload failed: {str(e)}"
            )

class InstagramUploader:
    def __init__(self):
        self.access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
        self.ig_user_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
        self.api_version = "v19.0"
        self.base_url = f"https://graph.facebook.com/{self.api_version}"
        # NOTE: Video uploads go to a different, special subdomain
        self.graph_video_url = f"https://graph-video.facebook.com/{self.api_version}"

        if not self.access_token or not self.ig_user_id:
            raise ValueError("Missing INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_BUSINESS_ACCOUNT_ID in .env file")

    def upload_reel(self, video_path: str, caption: str) -> dict:
        """Upload using the resumable upload protocol"""
        try:
            # --- Step 1: Initialize an Upload Session ---
            init_url = f"{self.base_url}/{self.ig_user_id}/media"
            init_payload = {
                'media_type': 'REELS',
                'upload_type': 'resumable',
                'access_token': self.access_token
            }
            init_response = requests.post(init_url, data=init_payload)
            init_response.raise_for_status()
            upload_session_id = init_response.json()['id']
            logger.info(f"SUCCESS: Step 1 - Initialized upload session: {upload_session_id}")

            # --- Step 2: Upload the Video File ---
            upload_url = f"{self.graph_video_url}/{upload_session_id}"
            headers = {
                'Authorization': f'OAuth {self.access_token}',
                'file_offset': '0'
            }
            with open(video_path, 'rb') as video_file:
                upload_response = requests.post(upload_url, headers=headers, data=video_file)
            upload_response.raise_for_status()
            logger.info(f"SUCCESS: Step 2 - Video data uploaded successfully.")

            # --- Step 3: Publish the Video ---
            publish_url = f"{self.base_url}/{self.ig_user_id}/media_publish"
            publish_payload = {
                'creation_id': upload_session_id,
                'caption': caption,
                'access_token': self.access_token
            }
            
            publish_response = requests.post(publish_url, data=publish_payload)
            publish_response.raise_for_status()
            
            final_container_id = publish_response.json()['id']
            logger.info(f"SUCCESS: Step 3 - Publishing command sent. Now waiting for completion. Container ID: {final_container_id}")
            
            # --- Step 4: Poll for Publishing Completion ---
            status_check_url = f"{self.base_url}/{final_container_id}"
            status_params = {'fields': 'status_code', 'access_token': self.access_token}
            
            for _ in range(20): # Poll for up to 100 seconds
                time.sleep(5)
                status_response = requests.get(status_check_url, params=status_params).json()
                status_code = status_response.get('status_code')
                logger.info(f"Publishing status: {status_code}")
                if status_code == 'FINISHED':
                    logger.info("VICTORY: Publishing is complete!")
                    
                    # --- Step 5: Get Permalink ---
                    permalink_url = f"{self.base_url}/{final_container_id}"
                    permalink_params = {'fields': 'permalink', 'access_token': self.access_token}
                    permalink_response = requests.get(permalink_url, params=permalink_params)
                    permalink = permalink_response.json().get('permalink', 'N/A')
                    
                    return {"success": True, "media_id": final_container_id, "permalink": permalink}

                if status_code == 'ERROR':
                    logger.error(f"Reel publishing failed. Check details in Meta Business Suite. Full error: {status_response}")
                    raise HTTPException(status_code=500, detail="Reel publishing failed on Instagram's side.")
            
            raise HTTPException(status_code=408, detail="Reel publishing timed out.")

        except requests.RequestException as e:
            error_details = "No response from server."
            if e.response is not None:
                try: error_details = e.response.json()
                except json.JSONDecodeError: error_details = e.response.text
            logger.error(f"Instagram API request error: {error_details}")
            raise HTTPException(status_code=400, detail=f"Instagram API error: {error_details}")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

    def upload_reel_via_ngrok(self, public_video_url: str, caption: str) -> dict:
        """Alternative upload method using public URL (via ngrok)"""
        try:
            # --- Step 1: Create Media Container ---
            logger.info(f"Step 1: Creating container with public URL: {public_video_url}")
            container_url = f"{self.base_url}/{self.ig_user_id}/media"
            container_payload = {
                'media_type': 'REELS',
                'video_url': public_video_url,
                'caption': caption,
                'access_token': self.access_token
            }
            container_response = requests.post(container_url, data=container_payload)
            container_response.raise_for_status()
            creation_id = container_response.json()['id']
            logger.info(f"✅ SUCCESS: Step 1 - Container created with ID: {creation_id}")

            # --- Step 2: Poll for Container Readiness ---
            status_check_url = f"{self.base_url}/{creation_id}"
            status_params = {'fields': 'status_code', 'access_token': self.access_token}
            
            for i in range(20): # Poll for up to 100 seconds
                time.sleep(5)
                status_response = requests.get(status_check_url, params=status_params).json()
                status_code = status_response.get('status_code')
                logger.info(f"Polling attempt {i+1}/20: Container status is {status_code}")
                
                if status_code == 'FINISHED':
                    # --- Step 3: Publish the Container ---
                    logger.info(f"Step 3: Publishing container {creation_id}...")
                    publish_url = f"{self.base_url}/{self.ig_user_id}/media_publish"
                    publish_payload = {'creation_id': creation_id, 'access_token': self.access_token}
                    publish_response = requests.post(publish_url, data=publish_payload)
                    publish_response.raise_for_status()
                    media_id = publish_response.json()['id']
                    
                    # --- VICTORY ---
                    logger.info(f"🏆 VICTORY! Reel has been published. Media ID: {media_id}")
                    permalink_url = f"{self.base_url}/{media_id}"
                    permalink_params = {'fields': 'permalink', 'access_token': self.access_token}
                    permalink_response = requests.get(permalink_url, params=permalink_params)
                    permalink = permalink_response.json().get('permalink', 'N/A')
                    
                    return {"success": True, "media_id": media_id, "permalink": permalink}

                if status_code == 'ERROR':
                    logger.error(f"Container processing failed. Full error from Instagram: {status_response}")
                    raise HTTPException(status_code=500, detail="Reel processing failed on Instagram's side.")
            
            raise HTTPException(status_code=408, detail="Reel publishing timed out.")

        except requests.RequestException as e:
            error_details = "No response from server."
            if e.response is not None:
                try: error_details = e.response.json()
                except Exception: error_details = e.response.text
            logger.error(f"Instagram API request error: {error_details}")
            raise HTTPException(status_code=400, detail=f"Instagram API error: {error_details}")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

# Initialize uploaders
youtube_uploader = YouTubeUploader()
instagram_uploader = InstagramUploader()

def validate_video_file(file: UploadFile) -> bool:
    """Validate uploaded video file."""
    # Check file size (max 2GB for YouTube, 1GB for Instagram)
    max_size = 2 * 1024 * 1024 * 1024  # 2GB
    
    # Check content type
    allowed_types = [
        "video/mp4", "video/avi", "video/mov", "video/wmv",
        "video/flv", "video/webm", "video/mkv"
    ]
    
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types: {allowed_types}"
        )
    
    return True

@app.post("/upload/youtube")
async def upload_to_youtube(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    tags: str = Form("")
):
    """Upload video to YouTube Shorts."""
    validate_video_file(file)
    
    # Parse tags
    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
        content = await file.read()
        temp_file.write(content)
        temp_path = temp_file.name
    
    try:
        result = youtube_uploader.upload_video(temp_path, title, description, tag_list)
        return JSONResponse(content=result)
    finally:
        # Clean up temporary file
        os.unlink(temp_path)

@app.post("/upload/instagram")
async def upload_to_instagram(
    file: UploadFile = File(...),
    caption: str = Form(""),
    method: str = Form("direct")
):
    """Upload video to Instagram Reels with option for direct or ngrok method."""
    validate_video_file(file)
    
    if method == "ngrok" and not public_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ngrok tunnel is not active. Cannot use ngrok method."
        )
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
        content = await file.read()
        temp_file.write(content)
        temp_path = temp_file.name
    
    try:
        if method == "ngrok":
            # Save to public directory
            file_extension = Path(file.filename).suffix or ".mp4"
            temp_filename = f"{uuid.uuid4()}{file_extension}"
            public_temp_path = TEMP_DIR / temp_filename
            
            try:
                shutil.copyfile(temp_path, public_temp_path)
                video_public_url = f"{public_url}/static/{temp_filename}"
                result = instagram_uploader.upload_reel_via_ngrok(video_public_url, caption)
                return JSONResponse(content=result)
            finally:
                if public_temp_path.exists():
                    os.unlink(public_temp_path)
        else:
            # Use direct upload method
            result = instagram_uploader.upload_reel(temp_path, caption)
            return JSONResponse(content=result)
    finally:
        # Clean up temporary file
        os.unlink(temp_path)

# MCP Tool Functions
@mcp.tool()
def post_to_youtube(title: str, description: str, tags: List[str], video_path: str) -> dict:
    """
    Post a video to YouTube Shorts.
    
    Args:
        title: Video title
        description: Video description
        tags: List of tags for the video
        video_path: Path to the video file
        
    Returns:
        Dict containing video_id, watch_url, and upload status
    """
    try:
        if not os.path.exists(video_path):
            return {"success": False, "error": "Video file not found"}
        
        result = youtube_uploader.upload_video(video_path, title, description, tags)
        return result
        
    except Exception as e:
        logger.error(f"MCP YouTube upload error: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
def post_to_instagram(caption: str, video_path: str, method: str = "direct") -> dict:
    """
    Post a video to Instagram Reels.
    
    Args:
        caption: Caption for the reel
        video_path: Path to the video file
        method: Upload method ("direct" or "ngrok")
        
    Returns:
        Dict containing reel_id, permalink, and upload status
    """
    try:
        if not os.path.exists(video_path):
            return {"success": False, "error": "Video file not found"}
        
        if method == "ngrok" and not public_url:
            return {"success": False, "error": "ngrok tunnel is not active"}
        
        if method == "ngrok":
            # Save to public directory
            file_extension = Path(video_path).suffix or ".mp4"
            temp_filename = f"{uuid.uuid4()}{file_extension}"
            public_temp_path = TEMP_DIR / temp_filename
            
            try:
                shutil.copyfile(video_path, public_temp_path)
                video_public_url = f"{public_url}/static/{temp_filename}"
                result = instagram_uploader.upload_reel_via_ngrok(video_public_url, caption)
                return result
            finally:
                if public_temp_path.exists():
                    os.unlink(public_temp_path)
        else:
            result = instagram_uploader.upload_reel(video_path, caption)
            return result
        
    except Exception as e:
        logger.error(f"MCP Instagram upload error: {e}")
        return {"success": False, "error": str(e)}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "message": "MCP Video Upload Server is running"}

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "MCP Video Upload Server",
        "version": "1.0.0",
        "endpoints": {
            "youtube_upload": "/upload/youtube",
            "instagram_upload": "/upload/instagram",
            "health": "/health"
        },
        "mcp_tools": ["post_to_youtube", "post_to_instagram"],
        "ngrok_status": "active" if public_url else "inactive",
        "ngrok_url": public_url if public_url else None
    }

# Include MCP routes
app.mount("/mcp", mcp)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True
    )