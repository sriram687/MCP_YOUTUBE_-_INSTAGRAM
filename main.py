import os
import time
import tempfile
import json
import logging
from typing import List, Optional
from pathlib import Path
import shutil
import uvicorn
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, status
from fastapi.responses import JSONResponse
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

# class InstagramUploader:
#     def __init__(self):
#         self.access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
#         self.app_id = os.getenv("INSTAGRAM_APP_ID")
#         self.app_secret = os.getenv("INSTAGRAM_APP_SECRET")
        
#         if not all([self.access_token, self.app_id, self.app_secret]):
#             raise ValueError("Missing Instagram API credentials in environment variables")
        
#         self.base_url = "https://graph.facebook.com/v18.0"

#     def upload_reel(self, video_path: str, caption: str) -> dict:
#         """Upload video as Instagram Reel and return reel details."""
#         try:
#             # Step 1: Get user's Instagram Business Account ID
#             user_response = requests.get(
#                 f"{self.base_url}/me/accounts",
#                 params={"access_token": self.access_token}
#             )
#             user_response.raise_for_status()
            
#             accounts = user_response.json().get("data", [])
#             if not accounts:
#                 raise HTTPException(
#                     status_code=status.HTTP_400_BAD_REQUEST,
#                     detail="No Facebook pages found. Link an Instagram Business Account to your Facebook page."
#                 )
            
#             page_id = accounts[0]["id"]  # Use first page
            
#             # Get Instagram account ID
#             ig_response = requests.get(
#                 f"{self.base_url}/{page_id}",
#                 params={
#                     "fields": "instagram_business_account",
#                     "access_token": self.access_token
#                 }
#             )
#             ig_response.raise_for_status()
            
#             ig_account = ig_response.json().get("instagram_business_account")
#             if not ig_account:
#                 raise HTTPException(
#                     status_code=status.HTTP_400_BAD_REQUEST,
#                     detail="No Instagram Business Account linked to this Facebook page."
#                 )
            
#             ig_account_id = ig_account["id"]
            
#             # Step 2: Upload video file to a temporary hosting service
#             # Note: For production, you'd want to upload to your own server/CDN
#             # For now, we'll assume the video is accessible via a public URL
#             # This is a simplified implementation - you'd need proper file hosting
            
#             # Step 3: Create Instagram media container for Reel
#             container_response = requests.post(
#                 f"{self.base_url}/{ig_account_id}/media",
#                 data={
#                     "media_type": "REELS",
#                     "video_url": f"file://{video_path}",  # This won't work in practice
#                     "caption": caption,
#                     "access_token": self.access_token
#                 }
#             )
            
#             # Note: Instagram requires a publicly accessible URL for the video
#             # In a real implementation, you'd upload the file to a CDN first
#             raise HTTPException(
#                 status_code=status.HTTP_501_NOT_IMPLEMENTED,
#                 detail="Instagram upload requires video to be hosted on a public URL. "
#                        "Please implement file hosting (CDN/server) for full functionality."
#             )
            
#         except requests.RequestException as e:
#             logger.error(f"Instagram API error: {e}")
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Instagram API error: {str(e)}"
#             )
#         except Exception as e:
#             logger.error(f"Unexpected error during Instagram upload: {e}")
#             raise HTTPException(
#                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#                 detail=f"Upload failed: {str(e)}"
#             )


# Make sure to have this at the top of your file

# ... other imports ...

# FINAL, CORRECTED InstagramUploader CLASS

# FINAL, VERIFIED Resumable Upload Class for Instagram Reels


# FINAL, OFFICIAL, AND VERIFIED Resumable Upload Class for Reels

# FINAL AND CORRECT - Official Resumable Upload Protocol for Reels

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
        try:
            # --- Step 1: Initialize an Upload Session ---
            # This tells Instagram you are about to send a video and gets an upload session ID.
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
            # This sends the actual video bytes to the special video server using the session ID.
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
            # This tells Instagram to process the uploaded video and make it a Reel.
            publish_url = f"{self.base_url}/{self.ig_user_id}/media_publish"
            publish_payload = {
                'creation_id': upload_session_id,
                'caption': caption,
                'access_token': self.access_token
            }
            
            # This can take a while, so we send the command and then wait for it to be ready.
            publish_response = requests.post(publish_url, data=publish_payload)
            publish_response.raise_for_status()
            
            # The publish call returns the ID of the final post container.
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
async def upload_to_youtube(  # Add async here
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
        content = await file.read()  # Add await here
        temp_file.write(content)
        temp_path = temp_file.name
    
    try:
        result = youtube_uploader.upload_video(temp_path, title, description, tag_list)
        return JSONResponse(content=result)
    finally:
        # Clean up temporary file
        os.unlink(temp_path)

@app.post("/upload/instagram")
async def upload_to_instagram(  # Add async
    file: UploadFile = File(...),
    caption: str = Form("")
):
    """Upload video to Instagram Reels."""
    validate_video_file(file)
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
        content = await file.read()  # Await the file read
        temp_file.write(content)  # Write bytes directly
        temp_path = temp_file.name
    
    try:
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
def post_to_instagram(caption: str, video_path: str) -> dict:
    """
    Post a video to Instagram Reels.
    
    Args:
        caption: Caption for the reel
        video_path: Path to the video file
        
    Returns:
        Dict containing reel_id, permalink, and upload status
    """
    try:
        if not os.path.exists(video_path):
            return {"success": False, "error": "Video file not found"}
        
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
        "mcp_tools": ["post_to_youtube", "post_to_instagram"]
    }

# Include MCP routes
# Correct
app.mount("/mcp", mcp) 

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        # ssl_keyfile=os.getenv("SSL_KEYFILE"),
        # ssl_certfile=os.getenv("SSL_CERTFILE")
    )