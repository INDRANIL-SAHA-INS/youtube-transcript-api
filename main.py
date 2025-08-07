from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from flask_cors import CORS
import json
import os
import requests
import random
import time

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Proxy management
PROXY_LIST = []
LAST_PROXY_UPDATE = 0
PROXY_UPDATE_INTERVAL = 3600  # Update proxies every hour

def get_free_proxies():
    """Fetch free proxy list from multiple sources"""
    proxies = []
    
    # Source 1: ProxyScrape API
    try:
        response = requests.get(
            "https://api.proxyscrape.com/v2/?request=get&format=textplain&protocol=http&timeout=10000&country=all",
            timeout=10
        )
        if response.status_code == 200:
            proxy_list = response.text.strip().split('\n')
            for proxy in proxy_list[:20]:  # Limit to first 20
                if ':' in proxy.strip():
                    proxies.append(proxy.strip())
    except:
        pass
    
    # Source 2: Free Proxy List
    try:
        response = requests.get(
            "https://www.proxy-list.download/api/v1/get?type=http",
            timeout=10
        )
        if response.status_code == 200:
            proxy_list = response.text.strip().split('\n')
            for proxy in proxy_list[:10]:  # Limit to first 10
                if ':' in proxy.strip():
                    proxies.append(proxy.strip())
    except:
        pass
    
    return list(set(proxies))  # Remove duplicates

def update_proxy_list():
    """Update the global proxy list if needed"""
    global PROXY_LIST, LAST_PROXY_UPDATE
    
    current_time = time.time()
    if current_time - LAST_PROXY_UPDATE > PROXY_UPDATE_INTERVAL or not PROXY_LIST:
        print("Updating proxy list...")
        PROXY_LIST = get_free_proxies()
        LAST_PROXY_UPDATE = current_time
        print(f"Updated proxy list with {len(PROXY_LIST)} proxies")

def get_random_proxy():
    """Get a random proxy from the list"""
    update_proxy_list()
    if PROXY_LIST:
        return random.choice(PROXY_LIST)
    return None

def test_proxy(proxy):
    """Test if a proxy is working"""
    try:
        proxy_dict = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}"
        }
        response = requests.get(
            "http://httpbin.org/ip", 
            proxies=proxy_dict, 
            timeout=10
        )
        return response.status_code == 200
    except:
        return False

@app.route('/')
def home():
    return jsonify({
        "message": "YouTube Transcript API Service",
        "usage": "/transcript?video_id=YOUR_VIDEO_ID",
        "status": "running",
        "features": [
            "Automatic proxy fallback for blocked IPs",
            "Smart error handling and retry logic",
            "Time-based transcript chunking",
            "Production-ready with Gunicorn"
        ],
        "endpoints": {
            "/transcript": "Get YouTube video transcript",
            "/health": "Service health check",
            "/proxy-status": "Check proxy system status"
        },
        "note": "This service automatically tries proxies if direct connection fails",
        "suggestions": [
            "Try different video IDs if one doesn't work",
            "Some videos work better than others",
            "Service automatically retries with proxies"
        ]
    })

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "service": "youtube-transcript-api",
        "timestamp": os.environ.get('RENDER_SERVICE_BUILD_COMMIT', 'local')
    })

@app.route('/proxy-status')
def proxy_status():
    """Check proxy system status"""
    update_proxy_list()
    
    # Test a few proxies
    working_proxies = 0
    if PROXY_LIST:
        test_sample = PROXY_LIST[:5]  # Test first 5 proxies
        for proxy in test_sample:
            if test_proxy(proxy):
                working_proxies += 1
    
    return jsonify({
        "total_proxies": len(PROXY_LIST),
        "tested_proxies": min(5, len(PROXY_LIST)),
        "working_proxies": working_proxies,
        "proxy_system": "enabled" if PROXY_LIST else "no_proxies_available",
        "last_update": LAST_PROXY_UPDATE,
        "next_update": LAST_PROXY_UPDATE + PROXY_UPDATE_INTERVAL
    })

def process_transcript(video_id):
    try:
        # Try direct connection first
        transcript_data = None
        error_occurred = None
        
        try:
            print(f"Attempting direct connection for video: {video_id}")
            ytt_api = YouTubeTranscriptApi()
            fetched_transcript = ytt_api.fetch(video_id)
            transcript_data = fetched_transcript.to_raw_data()
            print("Direct connection successful!")
            
        except Exception as e:
            error_occurred = e
            error_msg = str(e).lower()
            print(f"Direct connection failed: {error_msg}")
            
            # If blocked, try with proxies
            if any(keyword in error_msg for keyword in ["blocked", "ip", "cloud provider", "requests from your ip"]):
                print("Attempting to use proxy...")
                
                # Try up to 3 different proxies
                for attempt in range(3):
                    proxy = get_random_proxy()
                    if not proxy:
                        print("No proxies available")
                        break
                        
                    print(f"Trying proxy {attempt + 1}/3: {proxy}")
                    
                    # Test proxy first
                    if not test_proxy(proxy):
                        print(f"Proxy {proxy} is not working, trying next...")
                        continue
                    
                    try:
                        # YouTube Transcript API doesn't directly support proxies,
                        # but we can modify the underlying requests session
                        import requests
                        
                        # Create a custom session with proxy
                        session = requests.Session()
                        session.proxies = {
                            "http": f"http://{proxy}",
                            "https": f"http://{proxy}"
                        }
                        
                        # Monkey patch the session (this is a workaround)
                        original_get = requests.get
                        def patched_get(*args, **kwargs):
                            kwargs['proxies'] = session.proxies
                            kwargs['timeout'] = 15
                            return original_get(*args, **kwargs)
                        
                        requests.get = patched_get
                        
                        # Try with proxy
                        ytt_api = YouTubeTranscriptApi()
                        fetched_transcript = ytt_api.fetch(video_id)
                        transcript_data = fetched_transcript.to_raw_data()
                        
                        # Restore original function
                        requests.get = original_get
                        
                        print(f"Proxy {proxy} worked successfully!")
                        break
                        
                    except Exception as proxy_error:
                        print(f"Proxy {proxy} failed: {str(proxy_error)}")
                        # Restore original function in case of error
                        requests.get = original_get
                        continue
                
                # If all proxies failed
                if transcript_data is None:
                    return {
                        "success": False,
                        "error": "YouTube is blocking requests from this cloud server and all available proxies failed.",
                        "suggestion": "Try different videos or wait a few minutes. Some videos may work better than others.",
                        "technical_info": "Cloud providers like Render, Heroku, AWS are often blocked by YouTube's anti-bot measures.",
                        "solutions": [
                            "Try testing with different video IDs",
                            "Some videos work better than others", 
                            "Wait 10-15 minutes and try again",
                            "Consider using a VPS with residential IP instead of cloud hosting"
                        ],
                        "video_id": video_id,
                        "proxy_attempts": "Tried multiple proxies but all failed"
                    }, 503
            
            # Handle other types of errors
            elif "transcript" in error_msg and ("disabled" in error_msg or "not available" in error_msg):
                return {
                    "success": False,
                    "error": "Transcripts are not available for this video",
                    "video_id": video_id
                }, 404
            else:
                return {
                    "success": False,
                    "error": f"Error retrieving transcript: {str(error_occurred)}",
                    "video_id": video_id
                }, 500
        
        # Create time-based chunks with smart grouping
        target_chunk_duration = 30  # Target 30 seconds per chunk
        chunks = []
        current_segments = []
        
        for i, segment in enumerate(transcript_data):
            current_segments.append(segment)
            
            # Create a chunk when we reach target duration, have enough context, or it's the last segment
            if sum(seg['duration'] for seg in current_segments) >= target_chunk_duration or \
               len(current_segments) >= 5 or \
               i == len(transcript_data) - 1:
                
                chunk_text = " ".join(seg['text'] for seg in current_segments)
                start_time = current_segments[0]['start']
                end_time = current_segments[-1]['start'] + current_segments[-1]['duration']
                duration = float(end_time) - float(start_time)
                
                # Format timestamp once and reuse
                start_formatted = f"{int(start_time)//60:02d}:{int(start_time)%60:02d}"
                end_formatted = f"{int(end_time)//60:02d}:{int(end_time)%60:02d}"
                
                # Calculate words for analytics
                words = chunk_text.split()
                
                chunk = {
                    "id": len(chunks),
                    "text": chunk_text,
                    "timestamp": {
                        "start": int(start_time),
                        "end": int(end_time),
                        "duration": round(duration, 2),
                        "formatted": f"{start_formatted} - {end_formatted}"
                    },
                    "analytics": {
                        "word_count": len(words),
                        "speaking_rate": round(len(words) / duration, 2) if duration > 0 else 0
                    },
                    "embedding_text": f"At {start_formatted} to {end_formatted}: {chunk_text}"
                }
                
                chunks.append(chunk)
                current_segments = []

        response = {
            "success": True,
            "data": {
                "video_id": video_id,
                "metadata": {
                    "total_segments": len(transcript_data),
                    "total_chunks": len(chunks),
                    "duration": transcript_data[-1]['start'] + transcript_data[-1]['duration'],
                    "language": "en"
                },
                "transcript": {
                    "full_text": " ".join(segment['text'] for segment in transcript_data),
                    "segments": [
                        {
                            "id": i,
                            "text": segment['text'],
                            "start": segment['start'],
                            "duration": segment['duration'],
                            "timestamp": {
                                "seconds": int(segment['start']),
                                "formatted": f"{int(segment['start'])//60:02d}:{int(segment['start'])%60:02d}"
                            }
                        }
                        for i, segment in enumerate(transcript_data)
                    ],
                    "chunks": chunks
                }
            }
        }
        return response
    except Exception as e:
        return {"success": False, "error": str(e)}, 400

@app.route('/transcript', methods=['GET'])
def get_transcript():
    """API endpoint to get transcript for a YouTube video"""
    video_id = request.args.get('video_id')
    
    if not video_id:
        return jsonify({
            "success": False,
            "error": "Missing video_id parameter"
        }), 400
        
    result = process_transcript(video_id)
    if isinstance(result, tuple):  # Error case
        return jsonify(result[0]), result[1]
    return jsonify(result)

if __name__ == '__main__':
    # For local development only
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)