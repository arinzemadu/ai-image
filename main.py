import os
import requests
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from typing import Optional

app = FastAPI()

AIORNOT_API_KEY = os.environ.get("AIORNOT_API_KEY")
if not AIORNOT_API_KEY:
    raise ValueError("AIORNOT_API_KEY environment variable not set")

AIORNOT_API_BASE_URL = "https://api.aiornot.com"

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """
    Serves the main HTML page for media upload with styling and progress bar.
    """
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>AI Media Detector</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap');

            body {
                font-family: 'Roboto', sans-serif;
                background-color: #121212;
                color: #e0e0e0;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }

            .container {
                background: #1e1e1e;
                padding: 2em 3em;
                border-radius: 10px;
                box-shadow: 0 0 20px rgba(0, 255, 255, 0.1);
                text-align: center;
                width: 90%;
                max-width: 500px;
            }

            h1 {
                color: #00e5ff;
                font-weight: 300;
                margin-bottom: 1.5em;
                letter-spacing: 2px;
            }

            #uploadForm {
                display: flex;
                flex-direction: column;
                align-items: center;
            }

            input[type="file"] {
                display: none;
            }

            .file-upload-label {
                border: 2px dashed #444;
                border-radius: 5px;
                padding: 2em;
                cursor: pointer;
                transition: border-color 0.3s;
                width: 100%;
                margin-bottom: 1.5em;
            }

            .file-upload-label:hover {
                border-color: #00e5ff;
            }

            .file-upload-label span {
                font-weight: 300;
                color: #888;
            }
            
            #fileName {
                margin-top: -1em;
                margin-bottom: 1.5em;
                color: #00e5ff;
                font-weight: 400;
            }

            .upload-button {
                background: #00e5ff;
                color: #121212;
                border: none;
                padding: 0.8em 1.5em;
                border-radius: 5px;
                cursor: pointer;
                font-size: 1em;
                font-weight: 700;
                transition: background 0.3s, box-shadow 0.3s;
            }

            .upload-button:hover {
                background: #00b8cc;
                box-shadow: 0 0 10px rgba(0, 255, 255, 0.5);
            }

            #progress-container {
                width: 100%;
                background-color: #333;
                border-radius: 5px;
                margin-top: 1.5em;
                overflow: hidden;
                display: none;
            }

            #progress-bar {
                width: 0;
                height: 10px;
                background-color: #00e5ff;
                border-radius: 5px;
                transition: width 0.3s;
            }
            
            #progress-text {
                margin-top: 0.5em;
                font-size: 0.9em;
                color: #aaa;
                display: none;
            }

            #result {
                margin-top: 1.5em;
                font-size: 1.1em;
                font-weight: 400;
                line-height: 1.6;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>AI Media Detector</h1>
            <form id="uploadForm" enctype="multipart/form-data" method="post">
                <label for="file-upload" class="file-upload-label">
                    <span id="file-label-text">Click to browse or drag & drop a file</span>
                </label>
                <input id="file-upload" name="file" type="file" accept="image/*,video/*">
                <div id="fileName"></div>
                <button type="submit" class="upload-button">Analyze</button>
            </form>
            <div id="progress-container">
                <div id="progress-bar"></div>
            </div>
            <div id="progress-text"></div>
            <hr style="border-color: #333; margin: 2em 0; border-style: solid;">
            <div id="result"></div>
        </div>

        <script>
            const form = document.getElementById('uploadForm');
            const fileInput = document.getElementById('file-upload');
            const fileNameDisplay = document.getElementById('fileName');
            const fileLabel = document.querySelector('.file-upload-label');
            const fileLabelText = document.getElementById('file-label-text');
            const resultDiv = document.getElementById('result');
            const progressContainer = document.getElementById('progress-container');
            const progressBar = document.getElementById('progress-bar');
            const progressText = document.getElementById('progress-text');

            fileInput.addEventListener('change', (event) => {
                const file = event.target.files[0];
                if (file) {
                    fileNameDisplay.textContent = file.name;
                    fileLabelText.textContent = "File selected:";
                } else {
                    fileNameDisplay.textContent = '';
                    fileLabelText.textContent = "Click to browse or drag & drop a file";
                }
            });

            form.addEventListener('submit', async (event) => {
                event.preventDefault();
                const file = fileInput.files[0];
                if (!file) {
                    resultDiv.textContent = 'Please select a file to upload.';
                    return;
                }

                // Reset and show progress bar
                progressContainer.style.display = 'block';
                progressText.style.display = 'block';
                progressBar.style.width = '0%';
                progressText.textContent = 'Uploading...';
                resultDiv.textContent = '';

                const formData = new FormData();
                formData.append('file', file);

                const xhr = new XMLHttpRequest();
                xhr.open('POST', '/uploadfile/', true);

                xhr.upload.onprogress = (event) => {
                    if (event.lengthComputable) {
                        const percentComplete = (event.loaded / event.total) * 100;
                        progressBar.style.width = percentComplete + '%';
                    }
                };

                xhr.onload = () => {
                    progressText.textContent = 'Analyzing...';
                    // Indeterminate animation for analysis
                    progressBar.style.width = '100%';
                    progressBar.style.transition = 'none'; // To make the animation loop
                    let isAnalyzing = true;
                    
                    if (xhr.status >= 200 && xhr.status < 300) {
                        const data = JSON.parse(xhr.responseText);
                        resultDiv.innerHTML = `<strong>Analysis Result for ${data.filename}:</strong><br>${data.detection_result}`;
                    } else {
                        try {
                            const errorData = JSON.parse(xhr.responseText);
                            resultDiv.textContent = `Error: ${errorData.detail || xhr.statusText}`;
                        } catch (e) {
                             resultDiv.textContent = `Error: An unexpected error occurred (Status: ${xhr.status}).`;
                        }
                    }
                    
                    // Hide progress bar after completion/error
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
            
            // Drag and drop functionality
            fileLabel.addEventListener('dragover', (event) => {
                event.preventDefault();
                fileLabel.style.borderColor = '#00e5ff';
            });
            
            fileLabel.addEventListener('dragleave', (event) => {
                event.preventDefault();
                fileLabel.style.borderColor = '#444';
            });
            
            fileLabel.addEventListener('drop', (event) => {
                event.preventDefault();
                fileLabel.style.borderColor = '#444';
                const files = event.dataTransfer.files;
                if(files.length > 0) {
                    fileInput.files = files;
                    // Manually trigger the change event
                    const changeEvent = new Event('change');
                    fileInput.dispatchEvent(changeEvent);
                }
            });

        </script>
    </body>
    </html>
    """

@app.post("/uploadfile/")
async def create_upload_file(file: UploadFile = File(...)):
    """
    Handles file uploads and sends them to the AI or Not API for detection.
    """
    if not AIORNOT_API_KEY:
        raise HTTPException(status_code=500, detail="AIORNOT_API_KEY not configured on the server.")

    content = await file.read()

    headers = {
        "Authorization": f"Bearer {AIORNOT_API_KEY}",
        "accept": "application/json",
    }

    mime_type = file.content_type
    
    if mime_type.startswith("image/"):
        detection_endpoint = f"{AIORNOT_API_BASE_URL}/v2/image/sync"
    elif mime_type.startswith("video/"):
        # For video, AI or Not might require a two-step process (upload then poll)
        # For now, we'll return a message indicating it's not fully implemented.
        return {"filename": file.filename, "detection_result": "Video detection is not fully implemented yet."}
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type.")

    try:
        response = requests.post(
            detection_endpoint,
            headers=headers,
            files={'image': (file.filename, content, mime_type)}
        )
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        api_response = response.json()

        # Extract verdict and confidence from the nested structure
        verdict = api_response.get("report", {}).get("ai_generated", {}).get("verdict", "unknown")
        confidence = api_response.get("report", {}).get("ai_generated", {}).get("ai", {}).get("confidence", "N/A")
        
        detection_result = f"Verdict: {verdict.upper()}, Confidence: {confidence}"
        return {"filename": file.filename, "detection_result": detection_result}

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"AI or Not API request failed: {e}")
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"AI or Not API response missing key: {e}. Full response: {api_response}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")


