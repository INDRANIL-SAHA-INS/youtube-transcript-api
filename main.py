from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route('/')
def home():
    return jsonify({
        "message": "YouTube Transcript API Service",
        "usage": "/transcript?video_id=YOUR_VIDEO_ID"
    })

def process_transcript(video_id):
    try:
        ytt_api = YouTubeTranscriptApi()
        fetched_transcript = ytt_api.fetch(video_id)
        transcript_data = fetched_transcript.to_raw_data()
        
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
    # Run the Flask app
    app.run(port=5000, debug=True)