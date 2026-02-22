import os
import requests
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from typing import Optional, Dict, Any, List
from PIL import Image, ExifTags
from PIL.ExifTags import IFD
from io import BytesIO
import uuid
from starlette.responses import FileResponse
from pydantic import BaseModel
import json
import asyncio


app = FastAPI()

# API Keys and Base URLs
AIORNOT_API_KEY = os.environ.get("AIORNOT_API_KEY")
SIGHTENGINE_API_USER = os.environ.get("SIGHTENGINE_API_USER")
SIGHTENGINE_API_SECRET = os.environ.get("SIGHTENGINE_API_SECRET")

if not AIORNOT_API_KEY:
    raise ValueError("AIORNOT_API_KEY environment variable not set")
if not SIGHTENGINE_API_USER:
    raise ValueError("SIGHTENGINE_API_USER environment variable not set")
if not SIGHTENGINE_API_SECRET:
    raise ValueError("SIGHTENGINE_API_SECRET environment variable not set")


AIORNOT_API_BASE_URL = "https://api.aiornot.com"

TEMP_IMAGE_DIR = "/tmp/ai_media_detector_images"
os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)

def get_styles():
    return """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');
        :root {
            --primary-blue: #0056b3; /* A professional, slightly darker blue */
            --light-bg: #f8f9fa; /* Very light background */
            --container-bg: #ffffff; /* White for main content */
            --dark-text: #212529; /* Dark text for readability */
            --medium-text: #495057; /* Slightly lighter text for secondary info */
            --border-color: #dee2e6; /* Light gray border */
            --shadow-color: rgba(0, 0, 0, 0.1);
            --hover-blue: #004494; /* Darker blue on hover */
            --success-green: #28a745;
            --fail-red: #dc3545;
            --warning-orange: #ffc107;
        }
        body { 
            font-family: 'Inter', sans-serif; 
            background-color: var(--light-bg); 
            color: var(--dark-text); 
            display: flex; 
            flex-direction: column;
            align-items: center; 
            min-height: 100vh; 
            margin: 0; 
            padding: 2em; 
            box-sizing: border-box;
        }
        .container { 
            background: var(--container-bg); 
            padding: 2.5em 3.5em; 
            border-radius: 8px; /* Slightly less rounded for corporate feel */
            box-shadow: 0 4px 12px var(--shadow-color); 
            text-align: center; 
            width: 100%; 
            max-width: 800px; 
            margin-bottom: 2em;
        }
        h1 { 
            color: var(--primary-blue); 
            font-weight: 700; 
            margin-bottom: 1.5em; 
            letter-spacing: 0.02em; /* Softer letter spacing */
            text-transform: none; /* Default capitalization */
        }
        h2 { color: var(--dark-text); margin-bottom: 1em; }
        h3 { color: var(--primary-blue); margin-bottom: 0.8em; }

        nav { 
            width: 100%;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 2em;
            padding-bottom: 1em;
            display: flex;
            justify-content: center;
            gap: 1.5em;
        }
        nav a { 
            color: var(--medium-text); 
            text-decoration: none; 
            font-weight: 500; 
            transition: color 0.3s, border-bottom 0.3s;
            padding-bottom: 0.8em;
            border-bottom: 2px solid transparent;
        }
        nav a:hover { color: var(--primary-blue); }
        nav a.active { color: var(--primary-blue); border-bottom-color: var(--primary-blue); }
        
        #uploadForm { display: flex; flex-direction: column; align-items: center; gap: 1em; }
        input[type="file"] { display: none; }
        .file-upload-label { 
            border: 2px dashed var(--border-color); 
            border-radius: 8px; 
            padding: 3em; 
            cursor: pointer; 
            transition: all 0.3s; 
            width: 100%; 
            background-color: var(--light-bg); /* Light background for upload area */
            color: var(--medium-text);
            font-weight: 500;
        }
        .file-upload-label:hover { 
            border-color: var(--primary-blue); 
            background-color: #e9ecef; /* Slightly darker on hover */
            color: var(--dark-text);
        }
        #imagePreview { 
            max-width: 200px; 
            max-height: 200px; 
            object-fit: contain; 
            border: 1px solid var(--border-color);
            border-radius: 4px;
            padding: 5px;
            background-color: #ffffff; /* White background for image preview */
        }
        #fileName { 
            color: var(--primary-blue); 
            font-weight: 500; 
            margin-top: 0.5em; 
        }
        .primary-button, .secondary-button { 
            background: var(--primary-blue); 
            color: #ffffff; /* White text on buttons */
            border: none; 
            padding: 0.8em 1.8em; 
            border-radius: 5px; /* Slightly less rounded */
            cursor: pointer; 
            font-size: 1em; 
            font-weight: 700; 
            transition: all 0.3s; 
            box-shadow: 0 2px 5px var(--shadow-color);
            text-transform: none; /* Default capitalization */
            letter-spacing: 0;
        }
        .primary-button:hover, .secondary-button:hover { 
            background: var(--hover-blue); 
            box-shadow: 0 4px 8px var(--shadow-color); 
        }
        .secondary-button {
            background-color: var(--medium-text);
        }
        .secondary-button:hover {
            background-color: #6c757d;
        }

        #progress-container { 
            width: 100%; 
            background-color: var(--border-color); 
            border-radius: 8px; 
            margin-top: 1.5em; 
            overflow: hidden; 
            display: none; 
            height: 12px;
        }
        #progress-bar { 
            width: 0; 
            height: 100%; 
            background-color: var(--primary-blue); 
            border-radius: 8px; 
            transition: width 0.3s ease-out; 
        }
        #progress-text { 
            margin-top: 0.5em; 
            font-size: 0.9em; 
            color: var(--medium-text); 
            display: none; 
        }
        #result { 
            margin-top: 1.5em; 
            font-size: 1em; /* Slightly smaller for corporate look */
            line-height: 1.6; 
            text-align: left; 
            width: 100%;
        }
        .result-card { 
            background: var(--container-bg); 
            border: 1px solid var(--border-color); 
            padding: 1.5em; 
            border-radius: 8px; 
            margin-bottom: 1.5em; 
            box-shadow: 0 2px 8px var(--shadow-color);
        }
        .result-card h3 { 
            margin-top: 0; 
            color: var(--primary-blue); 
            margin-bottom: 0.8em; 
            border-bottom: 1px solid var(--border-color); 
            padding-bottom: 0.5em;
        }
        .api-results-table { 
            width: 100%; 
            border-collapse: collapse; 
            margin-bottom: 1em; 
            color: var(--dark-text); /* Dark text on light table background */
        }
        .api-results-table th, .api-results-table td { 
            padding: 0.8em; 
            text-align: left; 
            border-bottom: 1px solid var(--border-color); 
        }
        .api-results-table th { 
            font-weight: 700; 
            color: var(--medium-text); 
            text-transform: uppercase;
            font-size: 0.85em; /* Slightly smaller for professionalism */
        }
        .page-content p { 
            color: var(--medium-text); 
            font-size: 1em; 
            line-height: 1.6; 
            margin-bottom: 1em;
        }
        .page-content a { 
            color: var(--primary-blue); 
            text-decoration: none; 
            font-weight: 500; 
        }
        .page-content a:hover { text-decoration: underline; }

        .verdict-ai { color: var(--fail-red); font-weight: 700; }
        .verdict-human { color: var(--success-green); font-weight: 700; }
        .verdict-unknown { color: var(--warning-orange); font-weight: 700; } /* Use orange for unknown */
        .button-group {
            display: flex;
            gap: 1em;
            margin-top: 2em;
            justify-content: center;
        }
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
async def read_root():
    """Serves the main AI Media Detector page."""
    html_content = get_header("Media Detector") + """
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
    }

