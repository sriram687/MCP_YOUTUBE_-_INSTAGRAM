MCP Video Upload Server
A Model Context Protocol (MCP) compatible FastAPI server for uploading videos to YouTube Shorts and Instagram Reels.

Features
🎬 YouTube Shorts Upload: Automatic detection and upload of short-form videos
📱 Instagram Reels Upload: Direct upload to Instagram Business accounts
🔒 OAuth Authentication: Secure authentication with both platforms
🛡️ File Validation: Comprehensive video file validation
🔄 Token Refresh: Automatic refresh of expired access tokens
🌐 MCP Integration: Full MCP tool support for external integrations
📊 Error Handling: Structured JSON error responses
🚀 Production Ready: HTTPS support and comprehensive logging
Prerequisites
Python 3.8+
Google Cloud Platform Account with YouTube Data API v3 enabled
Meta for Developers Account with Instagram Graph API access
Instagram Business Account linked to a Facebook Page
Installation
Clone the repository and install dependencies:
bash
pip install -r requirements.txt
Copy and configure environment variables:
bash
cp .env.example .env
Edit .env file with your API credentials (see Configuration section below)
Configuration
YouTube API Setup
Create a Google Cloud Project:
Go to Google Cloud Console
Create a new project or select existing one
Enable the YouTube Data API v3
Create OAuth 2.0 Credentials:
Go to APIs & Services > Credentials
Create OAuth 2.0 Client ID (Web application)
Add authorized redirect URIs (e.g., http://localhost:8080/oauth2callback)
Generate Access and Refresh Tokens:
python
# Use Google's OAuth 2.0 Playground or implement OAuth flow
# https://developers.google.com/oauthplayground/
Add to .env:
env
YOUTUBE_CLIENT_ID=your_client_id
YOUTUBE_CLIENT_SECRET=your_client_secret
YOUTUBE_ACCESS_TOKEN=your_access_token
YOUTUBE_REFRESH_TOKEN=your_refresh_token
Instagram API Setup
Create a Meta App:
Go to Meta for Developers
Create a new app and add Instagram Graph API product
Configure Instagram Graph API:
Add Instagram Business Account to your Facebook Page
Generate access token with appropriate permissions:
instagram_basic
instagram_content_publish
pages_read_engagement
pages_show_list
Add to .env:
env
INSTAGRAM_ACCESS_TOKEN=your_access_token
INSTAGRAM_APP_ID=your_app_id
INSTAGRAM_APP_SECRET=your_app_secret
Running the Server
Development Mode
bash
python main.py
Or using uvicorn directly:

bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
Production Mode
bash
# With HTTPS (recommended)
uvicorn main:app --host 0.0.0.0 --port 443 --ssl-keyfile=/path/to/key.pem --ssl-certfile=/path/to/cert.pem

# Without HTTPS
uvicorn main:app --host 0.0.0.0 --port 8000
The server will be available at:

HTTP: http://localhost:8000
HTTPS: https://localhost:443 (if SSL configured)
API Endpoints
Upload to YouTube Shorts
POST /upload/youtube

Upload a video to YouTube, automatically detected as Short if under 60 seconds.

Request:

http
Content-Type: multipart/form-data

file: (video file)
title: "My Amazing Short Video"
description: "Check out this cool video! #Shorts"
tags: "short,video,awesome,content"
Response:

json
{
  "success": true,
  "video_id": "dQw4w9WgXcQ",
  "watch_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "is_short": true,
  "duration": 45.2
}
Upload to Instagram Reels
POST /upload/instagram

Upload a video as an Instagram Reel.

Request:

http
Content-Type: multipart/form-data

file: (video file)
caption: "Amazing reel content! #reels #instagram"
Response:

json
{
  "success": true,
  "reel_id": "17841234567890123",
  "permalink": "https://www.instagram.com/reel/ABC123DEF456/"
}
Health Check
GET /health

Check server status.

Response:

json
{
  "status": "healthy",
  "message": "MCP Video Upload Server is running"
}
MCP Tools
The server provides MCP-compatible tools that can be used by MCP clients:

post_to_youtube
python
post_to_youtube(
    title="My Video Title",
    description="Video description",
    tags=["tag1", "tag2", "tag3"],
    video_path="/path/to/video.mp4"
)
post_to_instagram
python
post_to_instagram(
    caption="My reel caption #reels",
    video_path="/path/to/video.mp4"
)
File Requirements
Supported Video Formats
MP4, AVI, MOV, WMV, FLV, WebM, MKV
File Size Limits
YouTube: Up to 2GB
Instagram: Up to 1GB
Video Specifications
YouTube Shorts: Vertical (9:16) or square (1:1), max 60 seconds
Instagram Reels: Vertical (9:16) recommended, 3-90 seconds
Error Handling
The server returns structured JSON error responses:

json
{
  "detail": "Error description",
  "status_code": 400
}
Common error codes:

400: Bad Request (invalid file, missing parameters)
401: Unauthorized (invalid credentials)
413: Payload Too Large (file size exceeded)
500: Internal Server Error
Security Considerations
Environment Variables: Never commit .env file to version control
HTTPS: Always use HTTPS in production
File Validation: Server validates file types and sizes
Token Security: Access tokens are refreshed automatically
CORS: Configure CORS policy for your domain in production
Troubleshooting
YouTube Upload Issues
"Invalid credentials": Check OAuth tokens and refresh
"Quota exceeded": YouTube API has daily quota limits
"Video processing failed": Check video format and size
Instagram Upload Issues
"Not implemented": Instagram requires public video URLs (see code comments)
"No business account": Ensure Instagram Business account is linked
"Invalid access token": Refresh Instagram access token
General Issues
Import errors: Install all requirements: pip install -r requirements.txt
Port conflicts: Change port in environment or command line
SSL errors: Check certificate paths and permissions
Development
Running Tests
bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest tests/
Code Formatting
bash
pip install black isort
black main.py
isort main.py
Contributing
Fork the repository
Create a feature branch
Make your changes
Add tests for new features
Submit a pull request
License
This project is licensed under the MIT License.

Support
For issues and questions:

Check the troubleshooting section
Review API documentation for YouTube and Instagram
Create an issue on the repository
