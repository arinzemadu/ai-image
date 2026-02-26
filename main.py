import os
import requests
import secrets
import json
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Annotated
from io import BytesIO

from dotenv import load_dotenv
load_dotenv() # Load variables from .env if it exists

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from fastapi.encoders import jsonable_encoder

from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import JWTError, jwt

from httpx_oauth.clients.google import GoogleOAuth2

from PIL import Image, ExifTags
from PIL.ExifTags import IFD
from starlette.responses import FileResponse
from pydantic import BaseModel

from database import SessionLocal, engine
from models import Base, User # Import Base from local models

# Define API keys from environment variables
AIORNOT_API_KEY = os.environ.get("AIORNOT_API_KEY")
SIGHTENGINE_API_USER = os.environ.get("SIGHTENGINE_API_USER")
SIGHTENGINE_API_SECRET = os.environ.get("SIGHTENGINE_API_SECRET")

# Create all tables (only for development/initial setup, Alembic should manage in production)
Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- Configuration for Google OAuth and JWT ---
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_urlsafe(32)) # Generate a strong secret key if not set
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

if not GOOGLE_CLIENT_ID:
    raise ValueError("GOOGLE_CLIENT_ID environment variable not set")
if not GOOGLE_CLIENT_SECRET:
    raise ValueError("GOOGLE_CLIENT_SECRET environment variable not set")

google_oauth_client = GoogleOAuth2(
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
)

# --- FastAPI Security ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Dependency to get DB session ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- JWT Functions ---
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- Pydantic Models for Authentication ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class UserInDB(User): # Reusing SQLAlchemy User model for Pydantic
    pass

# --- User Authentication Functions ---
def get_user(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def authenticate_user(db: Session, email: str) -> Optional[User]:
    user = get_user(db, email)
    if not user:
        return None
    return user

async def get_current_user(request: Request, db: Annotated[Session, Depends(get_db)]):
    token = request.cookies.get("access_token")
    if not token:
        # Fallback to Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
        
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    user = get_user(db, email=token_data.email)
    if user is None:
        raise credentials_exception
    return user


AIORNOT_API_BASE_URL = "https://api.aiornot.com"

TEMP_IMAGE_DIR = "/tmp/ai_media_detector_images"
os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)

def get_styles():
    return """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');
        :root {
            --primary-accent: #00e6e6; /* Vibrant Cyan/Electric Blue */
            --secondary-accent: #8e2de2; /* Deep Purple for contrast/gradients */
            --dark-background: #0d1117; /* Darkest background */
            --card-background: #161b22; /* Slightly lighter dark for cards */
            --text-light: #e6edf3; /* Off-white for main text */
            --text-medium: #8b949e; /* Gray for secondary text */
            --border-glow: #00e6e6; /* Accent color for glows */
            --shadow-subtle: rgba(0, 230, 230, 0.1); /* Subtle glow shadow */
            --button-shadow: rgba(0, 230, 230, 0.4); /* Stronger glow for buttons */
            --success-color: #388e3c; /* Green for success */
            --fail-color: #d32f2f; /* Red for failure */
            --warning-color: #fbc02d; /* Yellow for warning */
        }
        body { 
            font-family: 'Inter', sans-serif; 
            background-color: var(--dark-background); 
            color: var(--text-light); 
            display: flex; 
            flex-direction: column;
            align-items: center; 
            min-height: 100vh; 
            margin: 0; 
            padding: 2em; 
            box-sizing: border-box;
        }
        .container { 
            background: var(--card-background); 
            padding: 2.5em 3.5em; 
            border-radius: 10px; 
            border: 1px solid rgba(0, 230, 230, 0.3); /* Subtle accent border */
            box-shadow: 0 0 25px var(--shadow-subtle); 
            text-align: center; 
            width: 100%; 
            max-width: 800px; 
            margin-bottom: 2em;
        }
        h1 { 
            color: var(--primary-accent); 
            font-weight: 700; 
            margin-bottom: 1.5em; 
            letter-spacing: 0.08em; /* Slightly wider for techy feel */
            text-transform: uppercase;
            text-shadow: 0 0 8px rgba(0, 230, 230, 0.5); /* Subtle glow */
        }
        h2 { color: var(--text-light); margin-bottom: 1em; }
        h3 { color: var(--primary-accent); margin-bottom: 0.8em; }

        nav { 
            width: 100%;
            border-bottom: 1px solid rgba(0, 230, 230, 0.2);
            margin-bottom: 2em;
            padding-bottom: 1em;
            display: flex;
            justify-content: center;
            gap: 1.5em;
        }
        nav a { 
            color: var(--text-medium); 
            text-decoration: none; 
            font-weight: 500; 
            transition: color 0.3s, border-bottom 0.3s;
            padding-bottom: 0.8em;
            border-bottom: 2px solid transparent;
        }
        nav a:hover { color: var(--primary-accent); border-bottom-color: var(--primary-accent); }
        nav a.active { color: var(--primary-accent); border-bottom-color: var(--primary-accent); }
        
        #uploadForm { display: flex; flex-direction: column; align-items: center; gap: 1.5em; }
        input[type="file"] { display: none; }
        .file-upload-label { 
            border: 2px dashed var(--border-glow); 
            border-radius: 10px; 
            padding: 3em; 
            cursor: pointer; 
            transition: all 0.3s ease-in-out; 
            width: 100%; 
            background-color: var(--dark-background);
            color: var(--text-medium);
            font-weight: 500;
            text-shadow: 0 0 5px rgba(0, 230, 230, 0.3);
            box-shadow: 0 0 15px rgba(0, 230, 230, 0.2);
        }
        .file-upload-label:hover { 
            border-color: var(--secondary-accent); 
            background-color: #1a1f2c; 
            color: var(--text-light);
            box-shadow: 0 0 20px rgba(142, 45, 226, 0.4);
            text-shadow: 0 0 8px rgba(142, 45, 226, 0.5);
        }
        #imagePreview { 
            max-width: 200px; 
            max-height: 200px; 
            object-fit: contain; 
            border: 1px solid var(--border-glow);
            border-radius: 5px;
            padding: 5px;
            background-color: var(--dark-background);
            box-shadow: 0 0 10px var(--shadow-subtle);
        }
        #fileName { 
            color: var(--primary-accent); 
            font-weight: 500; 
            margin-top: 0.5em; 
            text-shadow: 0 0 5px rgba(0, 230, 230, 0.3);
        }
        .primary-button, .secondary-button { 
            background: linear-gradient(90deg, var(--primary-accent) 0%, var(--secondary-accent) 100%); 
            color: var(--text-light); 
            border: none; 
            padding: 0.8em 2.2em; 
            border-radius: 8px; 
            cursor: pointer; 
            font-size: 1em; 
            font-weight: 700; 
            transition: all 0.4s ease-in-out; 
            box-shadow: 0 0 20px var(--button-shadow);
            text-transform: uppercase;
            letter-spacing: 0.1em;
            position: relative;
            overflow: hidden;
        }
        .primary-button:hover, .secondary-button:hover { 
            transform: translateY(-2px);
            box-shadow: 0 0 30px var(--button-shadow);
        }
        .primary-button::before, .secondary-button::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            transition: all 0.7s ease-in-out;
        }
        .primary-button:hover::before, .secondary-button:hover::before {
            left: 100%;
        }
        .secondary-button {
            background: var(--text-medium); /* Muted gray for secondary */
            box-shadow: 0 0 10px rgba(139, 148, 158, 0.3);
            letter-spacing: 0.05em;
        }
        .secondary-button:hover {
            background: #a0a0a0;
            box-shadow: 0 0 20px rgba(139, 148, 158, 0.5);
        }

        #progress-container { 
            width: 100%; 
            background-color: var(--card-background); 
            border-radius: 8px; 
            margin-top: 1.5em; 
            overflow: hidden; 
            display: none; 
            height: 12px;
            border: 1px solid rgba(0, 230, 230, 0.1);
        }
        #progress-bar { 
            width: 0; 
            height: 100%; 
            background: linear-gradient(90deg, var(--primary-accent), var(--secondary-accent)); 
            border-radius: 8px; 
            transition: width 0.3s ease-out; 
        }
        #progress-text { 
            margin-top: 0.5em; 
            font-size: 0.9em; 
            color: var(--text-medium); 
            display: none; 
        }
        #result { 
            margin-top: 1.5em; 
            font-size: 1em; 
            line-height: 1.6; 
            text-align: left; 
            width: 100%;
        }
        .result-card { 
            background: var(--card-background); 
            border: 1px solid rgba(0, 230, 230, 0.2); 
            padding: 1.8em; 
            border-radius: 10px; 
            margin-bottom: 1.5em; 
            box-shadow: 0 0 20px var(--shadow-subtle);
        }
        .result-card h3 { 
            margin-top: 0; 
            color: var(--primary-accent); 
            margin-bottom: 0.8em; 
            border-bottom: 1px solid rgba(0, 230, 230, 0.1); 
            padding-bottom: 0.5em;
        }
        .api-results-table { 
            width: 100%; 
            border-collapse: collapse; 
            margin-bottom: 1em; 
            color: var(--text-light); 
        }
        .api-results-table th, .api-results-table td { 
            padding: 0.9em; 
            text-align: left; 
            border-bottom: 1px solid rgba(0, 230, 230, 0.1); 
        }
        .api-results-table th { 
            font-weight: 700; 
            color: var(--text-medium); 
            text-transform: uppercase;
            font-size: 0.8em; 
        }
        .page-content p { 
            color: var(--text-medium); 
            font-size: 1em; 
            line-height: 1.6; 
            margin-bottom: 1em;
        }
        .page-content a { 
            color: var(--primary-accent); 
            text-decoration: none; 
            font-weight: 500; 
            transition: color 0.3s;
        }
        .page-content a:hover { text-decoration: underline; color: var(--secondary-accent); }

        .verdict-ai { color: var(--fail-color); font-weight: 700; }
        .verdict-human { color: var(--success-color); font-weight: 700; }
        .verdict-unknown { color: var(--warning-color); font-weight: 700; } 
        .button-group {
            display: flex;
            gap: 1.5em;
            margin-top: 2.5em;
            justify-content: center;
        }
    </style>
    """

def get_header(active_page: str, request: Request):
    menu_items = {
        "Media Detector": "/",
        "Text Detector": "/aitext",
        "Roadmap": "/roadmap",
        "Pricing": "/pricing"
    }
    nav_links = ""
    for name, url in menu_items.items():
        is_active = "active" if name == active_page else ""
        nav_links += f'<a href="{url}" class="{is_active}">{name}</a>'
    
    # Add Login/Logout links dynamically
    access_token = request.cookies.get("access_token")
    if access_token:
        try:
            # Simple decode to show email
            payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
            user_email = payload.get("sub", "User")
            nav_links += f'<span style="color: var(--primary-accent); font-weight: 500;">{user_email}</span>'
            nav_links += '<a href="/logout">Logout</a>'
        except:
            nav_links += '<a href="/login">Login</a>'
    else:
        nav_links += '<a href="/login">Login</a>'
    
    return f"""
    <head>
        <title>AI Media Verification Hub</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        {get_styles()}
    </head>
    <body>
        <div class="container">
            <nav>{nav_links}</nav>
    """

def get_footer():
    return """
        </div>
    </body>
    </html>
    """

async def call_aiornot_api(content: bytes, filename: str, mime_type: str) -> Dict[str, Any]:
    """Function to call the AI or Not API."""
    try:
        headers = {"Authorization": f"Bearer {AIORNOT_API_KEY}", "accept": "application/json"}
        response = requests.post(f"{AIORNOT_API_BASE_URL}/v2/image/sync", headers=headers, files={'image': (filename, content, mime_type)})
        response.raise_for_status()
        api_response = response.json()
        verdict = api_response.get("report", {}).get("ai_generated", {}).get("verdict", "unknown")
        confidence = api_response.get("report", {}).get("ai_generated", {}).get("ai", {}).get("confidence", "N/A")
        return {"service": "AI or Not", "status": "Success", "verdict": verdict.capitalize(), "confidence": confidence}
    except Exception as e:
        return {"service": "AI or Not", "status": "Failed", "verdict": "Error", "confidence": 0}

async def call_sightengine_api(content: bytes, filename: str, mime_type: str) -> Dict[str, Any]:
    """Function to call the Sightengine API for AI-generated content detection."""
    try:
        # Sightengine API endpoint for image moderation
        # We'll use the 'ai-generated' model
        # Base API URL: https://api.sightengine.com/1.0/check.json
        # Parameters: api_user, api_secret, models=ai-generated
        
        API_URL = "https://api.sightengine.com/1.0/check.json"
        
        files = {'media': (filename, content, mime_type)}
        params = {
            'api_user': SIGHTENGINE_API_USER,
            'api_secret': SIGHTENGINE_API_SECRET,
            'models': 'genai'
        }

        response = requests.post(API_URL, files=files, params=params)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        api_response = response.json()

        verdict = "Unknown"
        confidence = 0.0

        if api_response and 'type' in api_response and 'ai_generated' in api_response['type']:
            # The 'ai_generated' is a float directly under 'type' in this response structure
            prob = api_response['type']['ai_generated'] 
            
            # Sightengine API often returns a probability directly for the genai model
            if prob is not None:
                # Assuming 'prob' directly represents the likelihood of being AI-generated
                if prob > 0.5: # Example threshold
                    verdict = "AI-Generated"
                    confidence = prob
                else:
                    verdict = "Human-Made"
                    # If it's not AI-generated, confidence in being human-made is 1 - prob
                    confidence = 1.0 - prob 
            else:
                verdict = "Unknown (Prob not found in 'type'/'ai_generated')"
                confidence = 0.0
        else:
            verdict = "Unknown (API response missing 'type' or 'ai_generated' within 'type')"
            confidence = 0.0
            print(f"DEBUG: Sightengine API - 'type' or 'ai_generated' key missing. Full API Response: {api_response}")        
        return {"service": "Sightengine AI", "status": "Success", "verdict": verdict, "confidence": confidence}
    except Exception as e:
        print(f"DEBUG: Sightengine API Error: {e}")
        return {"service": "Sightengine AI", "status": "Failed", "verdict": f"Error: {e}", "confidence": 0}





@app.get("/temp_images/{image_name}")
async def serve_temp_image(image_name: str):
    file_path = os.path.join(TEMP_IMAGE_DIR, image_name)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Image not found")

async def get_exif_data(content: bytes) -> str:
    try:
        image = Image.open(BytesIO(content))
        exif_data = image.getexif()
        if not exif_data:
            return "<strong>Warning:</strong> No EXIF data detected in this image.<br>"
        exif_info = "<strong>EXIF Data:</strong><br>"
        for tag_id, value in exif_data.items():
            tag_name = ExifTags.TAGS.get(tag_id, tag_id)
            exif_info += f"{tag_name}: {value}<br>"
        gps_info = exif_data.get_ifd(IFD.GPSInfo)
        if gps_info:
            lat = convert_dms_to_degrees(gps_info.get(2), gps_info.get(1))
            lon = convert_dms_to_degrees(gps_info.get(4), gps_info.get(3))
            if lat and lon:
                exif_info += f"GPS Location: <a href='https://www.google.com/maps?q={lat},{lon}' target='_blank'>View on Map</a><br>"
        return exif_info
    except Exception as e:
        return "Could not read EXIF data."

def convert_dms_to_degrees(dms, ref):
    if dms and ref and len(dms) == 3:
        degrees = dms[0]
        minutes = dms[1]
        seconds = dms[2]
        decimal_degrees = degrees + (minutes / 60.0) + (seconds / 3600.0)
        if ref in ['S', 'W']:
            decimal_degrees = -decimal_degrees
        return decimal_degrees
    return None

# --- Page Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serves the main AI Media Detector page, only for logged-in users."""
    access_token = request.cookies.get("access_token")
    if not access_token:
        return RedirectResponse(url="/login")
        
    try:
        # Verify the token is still valid
        jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
    except:
        # If token is invalid or expired, clear it and redirect to login
        response = RedirectResponse(url="/login")
        response.delete_cookie("access_token", samesite="lax")
        return response

    html_content = get_header("Media Detector", request) + """
        <h1>AI Media Verification Hub</h1>
        <form id="uploadForm" enctype="multipart/form-data" method="post">
            <label for="file-upload" class="file-upload-label"><span>Click to browse or drag & drop an image</span></label>
            <input id="file-upload" name="file" type="file" accept="image/*">
            <div id="fileName"></div>
            <img id="imagePreview" src="#" alt="Image Preview" style="max-width: 100%; height: auto; margin-top: 1em; margin-bottom: 1em; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); display: none;">
            <button type="submit" class="primary-button">Analyze</button>
        </form>
        <div id="progress-container"><div id="progress-bar"></div></div>
        <div id="progress-text"></div>
        <div id="result"></div>
    """ + get_footer()
    return html_content + """
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
    <script>
        const form = document.getElementById('uploadForm');
        const fileInput = document.getElementById('file-upload');
        const fileNameDisplay = document.getElementById('fileName');
        const fileLabel = document.querySelector('.file-upload-label');
        const imagePreview = document.getElementById('imagePreview'); // Get reference to the image preview
        const resultDiv = document.getElementById('result');
        const progressContainer = document.getElementById('progress-container');
        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress-text');

        fileInput.addEventListener('change', (event) => {
            const file = event.target.files[0];
            if (file) {
                fileNameDisplay.textContent = file.name;
                // Show image preview
                if (file.type.startsWith('image/')) {
                    const reader = new FileReader();
                    reader.onload = (e) => {
                        imagePreview.src = e.target.result;
                        imagePreview.style.display = 'block'; // Make image visible
                    };
                    reader.readAsDataURL(file);
                } else {
                    imagePreview.style.display = 'none'; // Hide if not an image
                    imagePreview.src = '#'; // Clear src
                }
            } else {
                fileNameDisplay.textContent = '';
                imagePreview.style.display = 'none'; // Hide if no file selected
                imagePreview.src = '#'; // Clear src
            }
        });

        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            const file = fileInput.files[0];
            if (!file) {
                resultDiv.textContent = 'Please select a file to upload.';
                return;
            }

            progressContainer.style.display = 'block';
            progressText.style.display = 'block';
            progressBar.style.width = '0%';
            progressText.textContent = 'Uploading...';
            resultDiv.innerHTML = '';

            const formData = new FormData();
            formData.append('file', file);

            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/uploadfile/', true);

            xhr.upload.onprogress = (event) => {
                if (event.lengthComputable) {
                    const percentComplete = (event.loaded / event.total) * 100;
                    progressBar.style.width = percentComplete + '%';
                    progressText.textContent = `Uploading... ${percentComplete.toFixed(0)}%`;
                }
            };

            xhr.onload = () => {
                progressText.textContent = 'Analyzing with multiple services...';
                
                if (xhr.status >= 200 && xhr.status < 300) {
                    const data = JSON.parse(xhr.responseText);
                    let resultHtml = `<h2>Verification Report for ${data.filename}</h2>`;

                    resultHtml += '<div class="result-card">';
                    resultHtml += '<h3>AI Detection Results</h3>';
                    resultHtml += '<table class="api-results-table"><thead><tr><th>Service</th><th>Verdict</th><th>Confidence</th></tr></thead><tbody>';
                    data.aggregated_results.forEach(res => {
                        const confidence = res.confidence !== undefined && res.confidence !== "N/A" ? `${(res.confidence * 100).toFixed(2)}%` : 'N/A';
                        resultHtml += `<tr><td>${res.service}</td><td>${res.verdict}</td><td>${confidence}</td></tr>`;
                    });
                    resultHtml += '</tbody></table></div>';
                    
                    resultHtml += '<div class="result-card">';
                    resultHtml += '<h3>Metadata & Origin</h3>';
                    resultHtml += data.exif_data;
                    if (data.google_reverse_search_url) {
                        resultHtml += `<br><a href="${data.google_reverse_search_url}" target="_blank">Search for this image on Google</a>`;
                    }
                    resultHtml += '</div>';

                    resultDiv.innerHTML = resultHtml;

                    // Add PDF generation button
                    const pdfButton = document.createElement('button');
                    pdfButton.className = 'primary-button';
                    pdfButton.textContent = 'Generate PDF Report';
                    pdfButton.id = 'generatePdfButton';
                    resultDiv.appendChild(pdfButton);

                    pdfButton.addEventListener('click', () => generatePdfReport(data.filename));
                } else {
                     resultDiv.textContent = `An error occurred during analysis (Status: ${xhr.status}).`;
                }
                
                progressContainer.style.display = 'none';
                progressText.style.display = 'none';
            };
            
            xhr.onerror = () => {
                resultDiv.textContent = 'An error occurred during the upload.';
                progressContainer.style.display = 'none';
                progressText.style.display = 'none';
            };

            xhr.send(formData);
        });

        function generatePdfReport(filename) {
            console.log("generatePdfReport called for filename:", filename);
            const { jsPDF } = window.jspdf;
            const doc = new jsPDF('p', 'pt', 'a4'); 
            const content = document.getElementById('result');
            console.log("Content element:", content);

            if (!content) {
                console.error("Content element for PDF generation not found!");
                return;
            }

            console.log("Starting html2canvas...");
            html2canvas(content, { 
                scale: 2, // Increase scale for better resolution in PDF
                useCORS: true // Important for images loaded from different origins (if any)
            }).then(canvas => {
                console.log("html2canvas generated canvas:", canvas);
                const imgData = canvas.toDataURL('image/png');
                console.log("Canvas toDataURL generated (first 50 chars):", imgData.substring(0, 50));

                const imgWidth = 595.28; // A4 width in points
                const pageHeight = 841.89; // A4 height in points
                const imgHeight = canvas.height * imgWidth / canvas.width;
                let heightLeft = imgHeight;

                let position = 0;

                doc.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight);
                heightLeft -= pageHeight;

                while (heightLeft >= 0) {
                    position = heightLeft - pageHeight; // Adjusted this line for correct pagination
                    doc.addPage();
                    doc.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight);
                    heightLeft -= pageHeight;
                }

                doc.save(`AI_Media_Report_${filename}.pdf`);
                console.log("PDF generated and saved.");
            }).catch(error => {
                console.error("Error generating PDF with html2canvas:", error);
            });
        }
    </script>
    """

@app.get("/aitext", response_class=HTMLResponse)
async def aitext_page(request: Request):
    """Serves the AI Text Detector 'Coming Soon' page."""
    html_content = get_header("Text Detector", request) + """
        <h1>AI Text Detector</h1>
        <div class="page-content">
            <p>Our state-of-the-art AI text detection tool is currently under development.</p>
            <p>This feature will allow you to analyze articles, documents, and other text-based content to determine the likelihood of it being AI-generated. We are committed to providing the same level of accuracy and detail as our media verification tools.</p>
            <p>Please check our <a href="/roadmap">Roadmap</a> for updates on this and other upcoming features.</p>
        </div>
    """ + get_footer()
    return html_content

@app.get("/roadmap", response_class=HTMLResponse)
async def roadmap_page(request: Request):
    """Serves the Roadmap page."""
    html_content = get_header("Roadmap", request) + """
        <h1>Product Roadmap 2026</h1>
        <div class="page-content" style="text-align: left;">
            <p>We are committed to building the most comprehensive and trustworthy media verification hub for professionals. Below is our planned feature release schedule for 2026.</p>
            
            <h3>Q1 2026: Text Checking Facility</h3>
            <ul>
                <li>Launch the initial version of our AI Text Detector.</li>
                <li>Users will be able to paste text to check for AI generation against our integrated APIs.</li>
            </ul>
            
            <h3>Q2 2026: Image Editing Analysis</h3>
            <ul>
                <li>Integrate perceptual hashing to detect sophisticated image manipulations and near-duplicates.</li>
                <li>Implement a "First Seen" database to track an image's first appearance and flag reused media.</li>
            </ul>

            <h3>Q3 2026: Video Verification & Expanded Sources</h3>
            <ul>
                <li>Introduce beta support for video file analysis to detect deepfakes and other AI manipulations.</li>
                <li>Continue further integration with additional AI detection sources to enhance the reliability of our aggregator.</li>
            </ul>

            <h3>Q4 2026: Proprietary AI Model</h3>
            <ul>
                <li>Begin the research and development phase for our own proprietary AI model, trained on a specialized dataset to provide a unique, in-house layer of verification for text, images, and video.</li>
            </ul>
        </div>
    """ + get_footer()
    return html_content

@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    """Serves the Pricing page."""
    html_content = get_header("Pricing", request) + """
        <h1>Pricing</h1>
        <div class="page-content" style="text-align: left;">
            <p>We offer a range of plans to suit the needs of different organizations, from individual journalists to large-scale newsrooms.</p>
            <h3>Free Tier</h3>
            <p><strong>$0/month</strong> - Includes 10 image analyses per month.</p>
            <h3>Basic</h3>
            <p><strong>$10/month</strong> - Includes 100 image analyses per month.</p>
            <h3>Professional</h3>
            <p><strong>$50/month</strong> - Includes 750 image analyses per month and priority support.</p>
            <h3>Enterprise</h3>
            <p><strong>Contact Us</strong> - For custom-volume plans, dedicated support, and advanced features.</p>
        </div>
    """ + get_footer()
    return html_content


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return HTMLResponse(content=f"""
        {get_header("Login", request)}
        <h1>Login</h1>
        <div class="page-content">
            <p>Please log in using your Google account to access all features.</p>
            <a href="/login/google" class="primary-button">Login with Google</a>
        </div>
        {get_footer()}
    """)

@app.get("/login/google")
async def login_google(request: Request):
    base_url = os.environ.get("BASE_URL", str(request.base_url).rstrip("/"))
    redirect_uri = f"{base_url}/auth/google/callback"
    print(f"DEBUG: login_google redirect_uri: {redirect_uri}")
    authorization_url = await google_oauth_client.get_authorization_url(redirect_uri)
    return RedirectResponse(authorization_url)

@app.get("/auth/google/callback", response_class=RedirectResponse)
async def auth_google_callback(
    request: Request,
    db: Annotated[Session, Depends(get_db)]
):
    try:
        code = request.query_params.get("code")
        if not code:
            print("DEBUG: Missing code in query parameters")
            raise HTTPException(status_code=400, detail="Missing code")
        
        base_url = os.environ.get("BASE_URL", str(request.base_url).rstrip("/"))
        redirect_uri = f"{base_url}/auth/google/callback"
        print(f"DEBUG: Using redirect_uri: {redirect_uri}")
        
        try:
            token = await google_oauth_client.get_access_token(code, redirect_uri)
            print("DEBUG: Successfully fetched access token")
            user_id, email = await google_oauth_client.get_id_email(token["access_token"])
            print(f"DEBUG: Fetched user email: {email}")
        except Exception as oauth_err:
            print(f"DEBUG: OAuth internal error type: {type(oauth_err)}")
            print(f"DEBUG: OAuth internal error: {oauth_err}")
            # If it has a response attribute (like GetIdEmailError), print the body
            if hasattr(oauth_err, "response"):
                print(f"DEBUG: Response status: {oauth_err.response.status_code}")
                print(f"DEBUG: Response body: {oauth_err.response.text}")
            raise HTTPException(status_code=400, detail=f"OAuth failed: {oauth_err}")
        
        if not email:
            raise HTTPException(status_code=400, detail="Google did not return an email.")
        
        user = db.query(User).filter(User.email == email).first()
        if not user:
            # Create new user
            user = User(email=email, subscription_plan="free", monthly_usage_count=0) # Add default values
            db.add(user)
            db.commit()
            db.refresh(user)

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email}, expires_delta=access_token_expires
        )
        
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="access_token", 
            value=access_token, 
            httponly=True, 
            max_age=int(access_token_expires.total_seconds()),
            samesite="lax"
        )
        return response
    except Exception as e:
        import traceback
        print(f"DEBUG: Exception in auth_google_callback: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")

@app.get("/logout", response_class=RedirectResponse)
async def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token", samesite="lax")
    return response

# --- API Endpoints ---

@app.post("/uploadfile/")
async def create_upload_file(
    current_user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...)
):
    """
    Handles file uploads and concurrently sends them to multiple AI detection services.
    """
    content = await file.read()
    
    # --- Gather Metadata and API Calls Concurrently ---
    exif_data_task = get_exif_data(content)
    aiornot_task = call_aiornot_api(content, file.filename, file.content_type)
    sightengine_task = call_sightengine_api(content, file.filename, file.content_type)

    results = await asyncio.gather(
        exif_data_task,
        aiornot_task,
        sightengine_task,
    )
    
    exif_data, aiornot_result, sightengine_result = results
    
    # --- Aggregate and Format Response ---
    aggregated_results = [aiornot_result, sightengine_result]

    # Save image temporarily to serve it for Google Reverse Image Search
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    temp_file_path = os.path.join(TEMP_IMAGE_DIR, unique_filename)
    with open(temp_file_path, "wb") as f:
        f.write(content)

    base_url = os.environ.get("BASE_URL", "")
    public_image_url = f"{base_url}/temp_images/{unique_filename}"
    google_reverse_search_url = f"https://www.google.com/searchbyimage?image_url={public_image_url}"
    
    return {
        "filename": file.filename,
        "aggregated_results": aggregated_results,
        "exif_data": exif_data,
        "google_reverse_search_url": google_reverse_search_url,
        "user_email": current_user.email
    }

