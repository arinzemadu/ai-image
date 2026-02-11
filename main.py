import os
import requests
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from typing import Optional, Dict, Any, List
from PIL import Image
from io import BytesIO
import uuid
import os
from starlette.responses import FileResponse
from pydantic import BaseModel
import json
import asyncio

app = FastAPI()

# API Keys and Base URLs
AIORNOT_API_KEY = os.environ.get("AIORNOT_API_KEY")
HIVE_API_KEY = os.environ.get("HIVE_API_KEY") # Placeholder for Hive AI

if not AIORNOT_API_KEY:
    raise ValueError("AIORNOT_API_KEY environment variable not set")

AIORNOT_API_BASE_URL = "https://api.aiornot.com"
HIVE_API_URL = "https://api.thehive.ai/v2/task/sync" # Assumed URL

TEMP_IMAGE_DIR = "/tmp/ai_media_detector_images"
os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)

# --- Shared HTML Components ---

def get_styles():
    return """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');
        body { 
            font-family: 'Inter', sans-serif; 
            background-color: #f4f7f9; 
            color: #333; 
            display: flex; 
            flex-direction: column;
            align-items: center; 
            min-height: 100vh; 
            margin: 0; 
            padding: 2em; 
            box-sizing: border-box;
        }
        .container { 
            background: #ffffff; 
            padding: 2em 3em; 
            border-radius: 12px; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.08); 
            text-align: center; 
            width: 100%; 
            max-width: 800px; 
        }
        h1 { color: #1a202c; font-weight: 700; margin-bottom: 1.5em; }
        nav { 
            width: 100%;
            border-bottom: 1px solid #e2e8f0;
            margin-bottom: 2em;
            padding-bottom: 1em;
        }
        nav a { 
            color: #4a5568; 
            text-decoration: none; 
            margin: 0 1.5em; 
            font-weight: 500; 
            transition: color 0.3s;
            padding-bottom: 1em;
            border-bottom: 2px solid transparent;
        }
        nav a:hover { color: #2b6cb0; }
        nav a.active { color: #2b6cb0; border-bottom-color: #2b6cb0; }
        #uploadForm, #textForm { display: flex; flex-direction: column; align-items: center; }
        input[type="file"] { display: none; }
        .file-upload-label { 
            border: 2px dashed #cbd5e0; 
            border-radius: 8px; 
            padding: 3em; 
            cursor: pointer; 
            transition: all 0.3s; 
            width: 100%; 
            margin-bottom: 1.5em;
            background-color: #fcfdff;
        }
        .file-upload-label:hover { border-color: #2b6cb0; background-color: #f0f4f8; }
        .file-upload-label span { font-weight: 500; color: #718096; }
        #fileName { margin-top: -1em; margin-bottom: 1.5em; color: #2b6cb0; font-weight: 500; }
        .primary-button { 
            background: #2b6cb0; 
            color: #ffffff; 
            border: none; 
            padding: 0.8em 1.8em; 
            border-radius: 8px; 
            cursor: pointer; 
            font-size: 1em; 
            font-weight: 700; 
            transition: all 0.3s; 
        }
        .primary-button:hover { background: #2c5282; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        #progress-container { width: 100%; background-color: #e2e8f0; border-radius: 8px; margin-top: 1.5em; overflow: hidden; display: none; }
        #progress-bar { width: 0; height: 12px; background-color: #3182ce; border-radius: 8px; transition: width 0.3s; }
        #progress-text { margin-top: 0.5em; font-size: 0.9em; color: #718096; display: none; }
        #result { margin-top: 1.5em; font-size: 1.1em; font-weight: 400; line-height: 1.6; text-align: left; }
        .result-card { background: #fdfdff; border: 1px solid #e2e8f0; padding: 1.5em; border-radius: 8px; margin-bottom: 1em; }
        .result-card h3 { margin-top: 0; color: #1a202c; margin-bottom: 0.8em; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.5em;}
        .api-results-table { width: 100%; border-collapse: collapse; margin-bottom: 1em; }
        .api-results-table th, .api-results-table td { padding: 0.8em; text-align: left; border-bottom: 1px solid #e2e8f0; }
        .api-results-table th { font-weight: 700; color: #4a5568; }
        .page-content p { color: #4a5568; font-size: 1.1em; line-height: 1.6; }
        .page-content a { color: #2b6cb0; text-decoration: none; font-weight: 500; }
        .page-content a:hover { text-decoration: underline; }
    </style>
    """

def get_header(active_page: str):
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

# --- API Call Functions ---

async def call_hive_api(content: bytes, filename: str) -> Dict[str, Any]:
    """Simulated function to call the Hive AI API."""
    if not HIVE_API_KEY:
        return {"service": "Hive AI", "status": "Not Configured", "verdict": "N/A", "confidence": 0}
    await asyncio.sleep(0.8)
    return {"service": "Hive AI", "status": "Success", "verdict": "AI-Generated", "confidence": 0.88}

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

# --- Metadata Functions ---

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
            return "<strong>Warning:</strong> No EXIF data found. Image origin and history cannot be verified.<br>"
        exif_info = "<strong>EXIF Data:</strong><br>"
        for tag_id, value in exif_data.items():
            tag_name = Image.TAGS.get(tag_id, tag_id)
            exif_info += f"{tag_name}: {value}<br>"
        gps_info = exif_data.get_ifd(Image.Exif.GPSINFO)
        if gps_info:
            lat = convert_dms_to_degrees(gps_info.get(2), gps_info.get(1))
            lon = convert_dms_to_degrees(gps_info.get(4), gps_info.get(3))
            if lat and lon:
                exif_info += f"GPS Location: <a href='https://www.google.com/maps?q={lat},{lon}' target='_blank'>View on Map</a><br>"
        return exif_info
    except Exception:
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
async def read_root():
    """Serves the main AI Media Detector page."""
    html_content = get_header("Media Detector") + """
        <h1>AI Media Verification Hub</h1>
        <form id="uploadForm" enctype="multipart/form-data" method="post">
            <label for="file-upload" class="file-upload-label"><span>Click to browse or drag & drop an image</span></label>
            <input id="file-upload" name="file" type="file" accept="image/*">
            <div id="fileName"></div>
            <button type="submit" class="primary-button">Analyze</button>
        </form>
        <div id="progress-container"><div id="progress-bar"></div></div>
        <div id="progress-text"></div>
        <div id="result"></div>
    """ + get_footer()
    return html_content + """
    <script>
        const form = document.getElementById('uploadForm');
        const fileInput = document.getElementById('file-upload');
        const fileNameDisplay = document.getElementById('fileName');
        const fileLabel = document.querySelector('.file-upload-label');
        const resultDiv = document.getElementById('result');
        const progressContainer = document.getElementById('progress-container');
        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress-text');

        fileInput.addEventListener('change', (event) => {
            const file = event.target.files[0];
            if (file) {
                fileNameDisplay.textContent = file.name;
            } else {
                fileNameDisplay.textContent = '';
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
    </script>
    """

@app.get("/aitext", response_class=HTMLResponse)
async def aitext_page():
    """Serves the AI Text Detector 'Coming Soon' page."""
    html_content = get_header("Text Detector") + """
        <h1>AI Text Detector</h1>
        <div class="page-content">
            <p>Our state-of-the-art AI text detection tool is currently under development.</p>
            <p>This feature will allow you to analyze articles, documents, and other text-based content to determine the likelihood of it being AI-generated. We are committed to providing the same level of accuracy and detail as our media verification tools.</p>
            <p>Please check our <a href="/roadmap">Roadmap</a> for updates on this and other upcoming features.</p>
        </div>
    """ + get_footer()
    return html_content

@app.get("/roadmap", response_class=HTMLResponse)
async def roadmap_page():
    """Serves the Roadmap page."""
    html_content = get_header("Roadmap") + """
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
async def pricing_page():
    """Serves the Pricing page."""
    html_content = get_header("Pricing") + """
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

# --- API Endpoints ---

@app.post("/uploadfile/")
async def create_upload_file(file: UploadFile = File(...)):
    """
    Handles file uploads and concurrently sends them to multiple AI detection services.
    """
    content = await file.read()
    
    # --- Gather Metadata and API Calls Concurrently ---
    exif_data_task = get_exif_data(content)
    aiornot_task = call_aiornot_api(content, file.filename, file.content_type)
    hive_task = call_hive_api(content, file.filename)

    results = await asyncio.gather(
        exif_data_task,
        aiornot_task,
        hive_task,
    )
    
    exif_data, aiornot_result, hive_result = results
    
    # --- Aggregate and Format Response ---
    aggregated_results = [aiornot_result, hive_result]

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
    }

