import os
import librosa
import soundfile as sf
import numpy as np
from pathlib import Path
from sarvamai import SarvamAI
import json
import time
from dotenv import load_dotenv

load_dotenv()

def sound_engineer_audio(audio_path, output_path):
    """
    Applies sound engineering to improve audio quality:
    - Normalize audio levels
    - Remove silence and background noise
    - Enhance speech clarity
    """
    print(f"  Sound engineering: {audio_path}")
    
    try:
        # Load audio (librosa handles MPEG, MP3, etc via audioread)
        y, sr = librosa.load(audio_path, sr=16000, mono=True)
        
        # 1. Normalize audio to prevent clipping
        y = librosa.util.normalize(y)
        
        # 2. Apply noise gate to remove very quiet background noise
        # Keep only sounds above a threshold
        threshold = 0.02
        y = np.where(np.abs(y) > threshold, y, 0)
        
        # 3. Apply noise reduction using spectral gating
        # Simple noise profile learning from first 0.5 seconds
        noise_duration = int(0.5 * sr)
        noise_sample = y[:noise_duration]
        noise_profile = np.mean(np.abs(librosa.stft(noise_sample)))
        
        # Reduce noise by scaling frequencies with low energy
        D = librosa.stft(y)
        magnitude = np.abs(D)
        phase = np.angle(D)
        magnitude = np.where(magnitude > noise_profile, magnitude, magnitude * 0.3)
        y = librosa.istft(magnitude * np.exp(1j * phase))
        
        # 4. Normalize again after processing
        y = librosa.util.normalize(y) * 0.95  # Leave headroom
        
        # 5. Remove silence at edges
        y, _ = librosa.effects.trim(y, top_db=40)
        
        # Save as WAV (soundfile supports WAV format universally)
        # Change extension to .wav for output
        output_wav = os.path.splitext(output_path)[0] + ".wav"
        sf.write(output_wav, y, sr, subtype='PCM_16')
        print(f"  ✓ Sound engineered to: {output_wav}")
        return output_wav
        
    except Exception as e:
        print(f"  ✗ Error processing audio: {e}")
        # Return original if engineering fails
        return audio_path


def get_processed_files(output_folder="transcriptions"):
    """
    Returns set of already processed filenames to avoid re-processing
    and wasting Sarvam AI credits.
    """
    processed = set()
    if os.path.exists(output_folder):
        for filename in os.listdir(output_folder):
            if filename.endswith(".json"):
                processed.add(filename.replace(".json", ""))
    return processed


def transcribe_with_sarvam(calls_folder="data/calls", output_folder="transcriptions", temp_folder="temp_processed"):
    """
    Transcribes audio files from calls folder using Sarvam AI:
    1. Does sound engineering on each call
    2. Uploads to Sarvam AI for transcription
    3. Saves results (manages credits by skipping already processed files)
    """
    
    # Create necessary folders
    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(temp_folder, exist_ok=True)
    
    # Initialize Sarvam AI client
    api_key = os.getenv("SARVAM_AI_API_KEY")
    if not api_key:
        raise ValueError("SARVAM_AI_API_KEY not found in .env file")
    
    client = SarvamAI(api_subscription_key=api_key)
    
    # Get list of already processed files to save credits
    processed_files = get_processed_files(output_folder)
    
    # Find all audio files in calls folder
    audio_extensions = [".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".flac", ".mpeg"]
    audio_files = []
    
    for filename in os.listdir(calls_folder):
        # Skip if already processed
        if os.path.splitext(filename)[0] in processed_files:
            print(f"⊘ Skipping (already processed): {filename}")
            continue
            
        if any(filename.lower().endswith(ext) for ext in audio_extensions):
            audio_files.append(os.path.join(calls_folder, filename))
    
    if not audio_files:
        print("No new audio files to process.")
        return
    
    print(f"\nProcessing {len(audio_files)} audio file(s)...\n")
    
    # Step 1: Sound engineer all files
    engineered_paths = []
    for audio_path in audio_files:
        filename = os.path.basename(audio_path)
        engineered_path = os.path.join(temp_folder, f"engineered_{filename}")
        engineered_path = sound_engineer_audio(audio_path, engineered_path)
        engineered_paths.append(engineered_path)
        time.sleep(0.5)  # Small delay to avoid overwhelming system
    
    print("\n" + "="*50)
    print("Creating Sarvam AI transcription job...")
    print("="*50 + "\n")
    
    # Filter out failed files before uploading to save credits
    valid_engineered_paths = []
    for i, audio_path in enumerate(audio_files):
        filename = os.path.basename(audio_path)
        engineered_path = engineered_paths[i]
        
        # Check if sound engineering actually succeeded
        if os.path.exists(engineered_path) and os.path.getsize(engineered_path) > 0:
            valid_engineered_paths.append(engineered_path)
        else:
            print(f"⊘ Skipping {filename} - sound engineering failed (file not created)")
    
    if not valid_engineered_paths:
        print("✗ No successfully engineered files to upload. Aborting to save credits.")
        return
    
    print(f"✓ {len(valid_engineered_paths)} file(s) ready for transcription\n")
    
    # Step 2: Create Sarvam AI batch job
    # Language: Gujarati (gu-IN) - will handle code-switching with Hindi and English automatically
    job = client.speech_to_text_job.create_job(
        model="saaras:v3",
        mode="transcribe",
        language_code="gu-IN",
        with_diarization=True,
        num_speakers=2
    )
    
    # Step 3: Upload engineered files to Sarvam AI
    try:
        job.upload_files(file_paths=valid_engineered_paths)
        print(f"✓ Uploaded {len(valid_engineered_paths)} audio file(s) to Sarvam AI")
        
        # Step 4: Start transcription job
        job.start()
        print("✓ Transcription job started")
        
        # Step 5: Wait for completion
        print("⏳ Waiting for Sarvam AI to complete transcription...")
        job.wait_until_complete()
        print("✓ Transcription complete!")
        
        # Step 6: Get results and check for errors BEFORE processing
        file_results = job.get_file_results()
        
        if not file_results or ('successful' not in file_results or len(file_results['successful']) == 0):
            print("✗ No successful transcriptions returned. Checking for errors...")
            if file_results and 'failed' in file_results and file_results['failed']:
                for f in file_results['failed']:
                    print(f"  ✗ {f['file_name']}: {f.get('error_message', 'Unknown error')}")
            print("⚠ Aborting to save remaining credits.")
            return
        
        print(f"\n✓ Successful: {len(file_results['successful'])}")
        for f in file_results['successful']:
            print(f"  ✓ {f['file_name']}")
        
        if file_results['failed']:
            print(f"\n✗ Failed: {len(file_results['failed'])}")
            for f in file_results['failed']:
                print(f"  ✗ {f['file_name']}: {f.get('error_message', 'Unknown error')}")
        
        # Step 7: Download actual output files (not just metadata)
        if file_results['successful']:
            temp_output = os.path.join(temp_folder, "sarvam_output")
            os.makedirs(temp_output, exist_ok=True)
            job.download_outputs(output_dir=temp_output)
            print(f"\n✓ Downloaded transcription files")
            
            # Debug: List all files in temp_output
            if os.path.exists(temp_output):
                downloaded_files = os.listdir(temp_output)
                print(f"  Found {len(downloaded_files)} file(s) in output: {downloaded_files}")
            
            # Step 8: Parse and save results
            print("\n" + "="*50)
            print("Processing transcriptions...")
            print("="*50 + "\n")
            
            # Read the actual transcription files
            for idx, result in enumerate(file_results['successful']):
                original_filename = result['file_name'].replace("engineered_", "")
                base_name = os.path.splitext(original_filename)[0]
                output_json_file = result.get('output_file', f"{idx}.json")
                
                # Read the actual output file
                output_json_path = os.path.join(temp_output, output_json_file)
                
                # If file doesn't exist with expected name, try to find any JSON
                if not os.path.exists(output_json_path) and os.path.exists(temp_output):
                    json_files = [f for f in os.listdir(temp_output) if f.endswith('.json')]
                    if idx < len(json_files):
                        output_json_path = os.path.join(temp_output, json_files[idx])
                
                if os.path.exists(output_json_path):
                    try:
                        with open(output_json_path, "r", encoding="utf-8") as f:
                            transcription_data = json.load(f)
                        
                        # Save full JSON response
                        output_json = os.path.join(output_folder, f"{base_name}.json")
                        with open(output_json, "w", encoding="utf-8") as f:
                            json.dump(transcription_data, f, indent=2, ensure_ascii=False)
                        
                        # Extract and save as readable TXT
                        output_txt = os.path.join(output_folder, f"{base_name}.txt")
                        with open(output_txt, "w", encoding="utf-8") as f:
                            f.write(f"File: {original_filename}\n")
                            f.write("="*60 + "\n\n")
                            
                            # Extract transcript from various possible field names
                            transcript = None
                            if "transcript" in transcription_data:
                                transcript = transcription_data["transcript"]
                            elif "transcription" in transcription_data:
                                transcript = transcription_data["transcription"]
                            elif "text" in transcription_data:
                                transcript = transcription_data["text"]
                            
                            if transcript:
                                f.write("TRANSCRIPT:\n")
                                f.write(transcript + "\n\n")
                            
                            # Save segments if available
                            segments = None
                            if "segments" in transcription_data:
                                segments = transcription_data["segments"]
                            
                            if segments:
                                f.write("SEGMENTS:\n")
                                for segment in segments:
                                    start = segment.get('start_time', segment.get('start', ''))
                                    end = segment.get('end_time', segment.get('end', ''))
                                    text = segment.get('text', segment.get('transcript', ''))
                                    if text:
                                        f.write(f"[{start} - {end}] {text}\n")
                        
                        print(f"  ✓ {base_name}")
                    except json.JSONDecodeError as e:
                        print(f"  ✗ {base_name} - JSON decode error: {e}")
                else:
                    print(f"  ✗ {base_name} - output file not found at {output_json_file}")
            print(f"  Output folder: {output_folder}")
        
    finally:
        # Keep temporary files for debugging
        print(f"\n✓ Temporary files saved in: {temp_folder}")


if __name__ == "__main__":
    transcribe_with_sarvam()
