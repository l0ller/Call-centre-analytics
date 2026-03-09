import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

def analyze_call_quality(transcription_text, diarized_transcript, file_name, client):
    """
    Uses Gemini API to analyze call quality for stock market advisory services.
    Evaluates: portfolio updates, advice quality, client satisfaction, compliance.
    Uses diarized transcript and lets Gemini identify agent vs client.
    """
    
    # Format diarized transcript with speaker IDs for Gemini to analyze
    formatted_diarized = "DIARIZED CALL TRANSCRIPT:\n"
    formatted_diarized += "="*60 + "\n"
    for entry in diarized_transcript:
        speaker_id = entry.get('speaker_id', '?')
        time_info = f"[{entry.get('start_time_seconds', 0):.1f}s]"
        formatted_diarized += f"{time_info} Speaker {speaker_id}: {entry.get('transcript', '')}\n"
    
    prompt = f"""Analyze the quality of this stock market advisory call and provide a detailed assessment.

Call File: {file_name}

{formatted_diarized}

FULL TRANSCRIPT:
{transcription_text}

CONTEXT: This is a call between a stock market advisory employee (the Agent) and their assigned client (the Client). 

IMPORTANT: You will see Speaker 0 and Speaker 1 in the transcript. Based on the conversation patterns, language, and topics discussed, please identify:
- Who is the Agent (giving advice, providing market updates, managing portfolio)?
- Who is the Client (asking questions, held shares, seeking advice)?

Then evaluate the following aspects and provide a score (1-10) for each:

1. **Portfolio Communication Clarity**: How clearly did the agent explain portfolio status, recent changes, and performance? Was the information easy to understand for the client?

2. **Quality of Investment Advice**: Were the buy/sell recommendations sound and well-justified? Did the agent explain the reasoning? Were recommendations suitable for the client's profile?

3. **Professionalism & Trustworthiness**: Did the agent demonstrate expertise and confidence? Was the tone appropriate for financial advisory? Did they avoid aggressive/pushy selling?

4. **Risk Awareness**: Did the agent mention risks associated with recommendations? Was there proper suitability assessment?

5. **Client Question Handling**: Were all client questions answered satisfactorily? Were answers accurate and complete?

6. **Opportunity Identification**: Did the agent identify relevant trading opportunities? Were recommendations aligned with market conditions?

7. **Relationship Building**: Did the agent build rapport and confidence? Would the client feel comfortable calling again or trusting future advice?

8. **Regulatory Compliance**: Was proper disclosure given? Were recommendations suitable? Was advice documented verbally?

Also provide:
- **Overall Quality Score** (1-10)
- **Agent Identity**: Which speaker (0 or 1) is the Agent and why?
- **Client Sentiment**: Analyze the client's tone and sentiment throughout the call (satisfied, concerned, confused, engaged, dismissive, etc.)
- **Agent's Key Strengths**: What the agent did well (clarity, engagement, suitable advice, risk disclosure, rapport building, etc.)
- **Client Satisfaction Assessment**: How satisfied/confident does the client seem at the end of call?
- **Areas for Improvement**: Where could advisor improve (clarity, risk disclosure, engagement, follow-up, etc.)
- **Trading Opportunities Missed**: Any missed opportunities to help the client with portfolio optimization
- **Compliance Concerns**: Any regulatory or suitability issues identified
- **Recommended Coaching Points**: Specific action items to improve agent's performance

Format your response as JSON with these exact keys: clarity_score, advice_quality_score, professionalism_score, risk_awareness_score, question_handling_score, opportunity_identification_score, relationship_score, compliance_score, overall_score, agent_identity, client_sentiment, agent_strengths, client_satisfaction, improvements, missed_opportunities, compliance_concerns, coaching_points"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    
    return response.text


def parse_quality_response(response_text):
    """
    Attempts to extract and properly parse JSON from Gemini's response.
    Handles markdown code blocks and escape sequences.
    """
    try:
        # Remove markdown code block markers if present
        response_text = response_text.replace("```json\n", "").replace("\n```", "").replace("```", "")
        
        # Try to find JSON in the response
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        
        if start_idx != -1 and end_idx > start_idx:
            json_str = response_text[start_idx:end_idx]
            
            # Try direct parsing first
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # If that fails, the string might be raw with escape sequences
                # Decode it properly
                import codecs
                decoded_str = codecs.decode(json_str, 'unicode_escape')
                return json.loads(decoded_str)
                
    except Exception as e:
        print(f"    Warning: Could not parse JSON response: {e}")
    
    # If JSON parsing fails, return the raw text
    return {"raw_response": response_text}


def analyze_call_quality_with_retry(transcription_text, diarized_transcript, file_name, client):
    """
    Wrapper function to handle rate limit errors with exponential backoff.
    Retries up to 3 times with exponential delays.
    """
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            return analyze_call_quality(transcription_text, diarized_transcript, file_name, client)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait_time = (2 ** attempt) * 15  # 15s, 30s, 60s
                print(f"  ⚠ Rate limited! Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                # Not a rate limit error, re-raise
                raise
    
    raise Exception("Max retries exceeded for rate limits.")


def verify_gemini_connection(client):
    """
    Verifies that Gemini 2.5 Flash API is accessible and working.
    Sends a minimal test request to check connectivity.
    """
    print("\n" + "="*50)
    print("Verifying Gemini API Connection...")
    print("="*50 + "\n")
    
    try:
        # A tiny request to test connectivity
        test_response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Hello"
        )
        print("✓ Verification Success: Gemini 2.5 Flash is active and accessible.")
        print(f"  Response: {test_response.text[:50]}...")
        print()
        return True
        
    except Exception as e:
        print(f"✗ Verification Failed: {e}")
        print(f"\nTroubleshooting:")
        print(f"  1. Check your Gemini_Api_Key in .env file")
        print(f"  2. Verify API is enabled in Google Cloud Console")
        print(f"  3. Check Free Tier rate limits (15 RPM, 1500 RPD)")
        print()
        return False


def analyze_all_calls(transcriptions_folder="transcriptions", output_folder="call_quality_reports"):
    """
    Analyzes quality of all transcribed calls and saves reports.
    Implements throttling (12s delay) to respect Free Tier rate limits.
    """
    
    # Setup
    os.makedirs(output_folder, exist_ok=True)
    
    # Initialize Gemini API
    api_key = os.getenv("Gemini_Api_Key")
    if not api_key:
        raise ValueError("Gemini_Api_Key not found in .env file")
    
    client = genai.Client(api_key=api_key)
    
    # Verify Gemini API connection before processing
    if not verify_gemini_connection(client):
        print("Cannot proceed without working Gemini API connection.")
        return
    
    # Get all JSON transcriptions (which have diarization)
    json_files = sorted(Path(transcriptions_folder).glob("*.json"))
    
    if not json_files:
        print("No transcription files found.")
        return
    
    # Filter out already analyzed files to skip re-analysis
    new_json_files = []
    already_analyzed = []
    
    for json_file in json_files:
        quality_file = Path(output_folder) / f"{json_file.stem}_quality.json"
        if quality_file.exists():
            already_analyzed.append(json_file.name)
        else:
            new_json_files.append(json_file)
    
    if already_analyzed:
        print(f"⊘ Skipping already analyzed ({len(already_analyzed)}):")
        for name in already_analyzed:
            print(f"  ✓ {name}")
        print()
    
    if not new_json_files:
        print("No new calls to analyze. All transcriptions have been processed.")
        return
    
    print(f"\nAnalyzing quality of {len(new_json_files)} new call(s)...\n")
    
    # Load existing summary to preserve already-analyzed calls
    quality_summary = {}
    summary_path = Path(output_folder) / "quality_summary.json"
    if summary_path.exists():
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                quality_summary = json.load(f)
        except:
            pass
    
    for json_file in new_json_files:
        print(f"Analyzing: {json_file.name}")
        
        try:
            # Read JSON transcription
            with open(json_file, "r", encoding="utf-8") as f:
                transcription_data = json.load(f)
            
            # Extract full transcript and diarized transcript
            full_transcript = transcription_data.get("transcript", "")
            diarized_entries = transcription_data.get("diarized_transcript", {}).get("entries", [])
            
            if not full_transcript:
                print(f"  ✗ No transcript found in {json_file.name}")
                continue
            
            # Get quality analysis from Gemini (with retry logic)
            print(f"  Requesting Gemini analysis...")
            quality_response = analyze_call_quality_with_retry(full_transcript, diarized_entries, json_file.name, client)
            
            # Parse response
            quality_data = parse_quality_response(quality_response)
            
            # Save quality report as JSON
            base_name = json_file.stem
            json_output_path = os.path.join(output_folder, f"{base_name}_quality.json")
            with open(json_output_path, "w", encoding="utf-8") as f:
                json.dump(quality_data, f, indent=2, ensure_ascii=False)
            
            # Save summary for report
            quality_summary[base_name] = quality_data
            
            print(f"  ✓ Quality report saved:")
            
            # Display key metrics if available
            if "overall_score" in quality_data:
                print(f"    Overall Score: {quality_data['overall_score']}/10")
            if "client_sentiment" in quality_data:
                print(f"    Client Sentiment: {quality_data['client_sentiment']}")
            
            # Throttle to respect Free Tier rate limits (15 RPM = 1 request every 4s)
            # Using 12s for safety to stay well under the limit
            if new_json_files.index(json_file) < len(new_json_files) - 1:  # Don't sleep after last file
                print(f"  ⏳ Throttling (12s delay)...")
                time.sleep(12)
            
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"  ✗ Rate limit exceeded for {json_file.name}")
                print(f"    Gemini Free Tier limit reached. Please wait 24 hours or upgrade to paid tier.")
                print(f"    Error: {e}")
            else:
                print(f"  ✗ Error analyzing {json_file.name}: {e}")
    
    # Save comprehensive summary
    summary_path = os.path.join(output_folder, "quality_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(quality_summary, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*50}")
    print(f"✓ Quality analysis complete!")
    print(f"  Output folder: {output_folder}")
    print(f"  Summary saved: {summary_path}")
    print(f"{'='*50}")


if __name__ == "__main__":
    analyze_all_calls()
