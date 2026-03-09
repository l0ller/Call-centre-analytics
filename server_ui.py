import os
import json
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import shutil
from datetime import datetime

# Import transcription and quality analysis functions
from transcribe import transcribe_with_sarvam
from call_quality_analyzer import analyze_all_calls

app = FastAPI()

# Directories
CALLS_DIR = Path("data/calls")
TRANSCRIPTIONS_DIR = Path("transcriptions")
QUALITY_REPORTS_DIR = Path("call_quality_reports")

# Create directories if they don't exist
CALLS_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
QUALITY_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """Serve the main dashboard"""
    return FileResponse("static/index.html")


@app.get("/api/calls")
async def get_calls():
    """Get list of all calls with their status"""
    calls = []
    
    try:
        # Get all audio files
        audio_extensions = [".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".flac", ".mpeg"]
        for file in CALLS_DIR.iterdir():
            if any(file.suffix.lower() == ext for ext in audio_extensions):
                base_name = file.stem
                
                # Check for transcription
                transcription_file = TRANSCRIPTIONS_DIR / f"{base_name}.json"
                has_transcription = transcription_file.exists()
                
                # Check for quality report
                quality_file = QUALITY_REPORTS_DIR / f"{base_name}_quality.json"
                has_quality = quality_file.exists()
                
                # Get file info
                file_stats = file.stat()
                upload_time = datetime.fromtimestamp(file_stats.st_mtime).isoformat()
                
                # Load quality score if exists
                quality_score = None
                if has_quality:
                    try:
                        with open(quality_file, "r", encoding="utf-8") as f:
                            quality_data = json.load(f)
                            quality_score = quality_data.get("overall_score")
                    except:
                        pass
                
                calls.append({
                    "name": file.name,
                    "base_name": base_name,
                    "uploaded_at": upload_time,
                    "file_size": file_stats.st_size,
                    "has_transcription": has_transcription,
                    "has_quality": has_quality,
                    "quality_score": quality_score,
                    "status": "Complete" if (has_transcription and has_quality) else 
                             "Transcribed" if has_transcription else 
                             "Uploaded"
                })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )
    
    return {"calls": sorted(calls, key=lambda x: x["uploaded_at"], reverse=True)}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload an audio file"""
    try:
        # Check file extension
        audio_extensions = [".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".flac", ".mpeg"]
        if not any(file.filename.lower().endswith(ext) for ext in audio_extensions):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(audio_extensions)}"
            )
        
        # Save file
        file_path = CALLS_DIR / file.filename
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return {
            "message": "File uploaded successfully",
            "filename": file.filename,
            "path": str(file_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/process")
async def process_calls():
    """Start transcription and quality analysis"""
    try:
        # Run transcription
        print("Starting transcription...")
        transcribe_with_sarvam()
        
        # Run quality analysis
        print("Starting quality analysis...")
        analyze_all_calls()
        
        return {"message": "Processing complete"}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.get("/api/call/{base_name}/transcription")
async def get_transcription(base_name: str):
    """Get transcription for a call"""
    try:
        transcription_file = TRANSCRIPTIONS_DIR / f"{base_name}.json"
        
        if not transcription_file.exists():
            raise HTTPException(status_code=404, detail="Transcription not found")
        
        with open(transcription_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/call/{base_name}/quality")
async def get_quality(base_name: str):
    """Get quality report for a call"""
    try:
        quality_file = QUALITY_REPORTS_DIR / f"{base_name}_quality.json"
        
        if not quality_file.exists():
            raise HTTPException(status_code=404, detail="Quality report not found")
        
        with open(quality_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/call/{base_name}")
async def delete_call(base_name: str):
    """Delete a call and its associated files"""
    try:
        # Find and delete the audio file
        audio_extensions = [".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".flac", ".mpeg"]
        audio_file = None
        for file in CALLS_DIR.iterdir():
            if file.stem == base_name and any(file.suffix.lower() == ext for ext in audio_extensions):
                audio_file = file
                break
        
        if audio_file:
            audio_file.unlink()
        
        # Delete transcription
        transcription_file = TRANSCRIPTIONS_DIR / f"{base_name}.json"
        if transcription_file.exists():
            transcription_file.unlink()
        
        # Delete quality report
        quality_file = QUALITY_REPORTS_DIR / f"{base_name}_quality.json"
        if quality_file.exists():
            quality_file.unlink()
        
        return {"message": "Call deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
