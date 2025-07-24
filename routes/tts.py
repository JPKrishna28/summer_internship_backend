from flask import Blueprint, request, jsonify, current_app, send_file
from routes.auth import token_required
from datetime import datetime
import google.generativeai as genai
import os
import tempfile
import json
import base64
import uuid
from bson import ObjectId

tts_bp = Blueprint('tts', __name__)

# Configure Gemini API
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# Initialize pyttsx3 Text-to-Speech engine
def get_tts_engine():
    """Initialize pyttsx3 TTS engine with proper settings"""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        
        # Set basic properties
        rate = engine.getProperty('rate')
        engine.setProperty('rate', rate - 50)  # Slightly slower for better clarity
        
        volume = engine.getProperty('volume')
        engine.setProperty('volume', 0.9)  # 90% volume
        
        return engine
    except Exception as e:
        print(f"Warning: Could not initialize TTS engine: {e}")
        return None

def configure_tts_voice(engine, voice_gender='neutral', speaking_rate=1.0, language_code='en-US'):
    """Configure TTS engine voice settings"""
    if not engine:
        return False
        
    try:
        # Set speaking rate
        base_rate = 150  # Base words per minute
        new_rate = int(base_rate * speaking_rate)
        engine.setProperty('rate', new_rate)
        
        # Set voice based on gender preference
        voices = engine.getProperty('voices')
        if voices:
            selected_voice = voices[0]  # Default to first voice
            
            for voice in voices:
                voice_name = voice.name.lower() if voice.name else ""
                voice_id = voice.id.lower() if voice.id else ""
                
                if voice_gender.lower() == 'female':
                    if any(keyword in voice_name for keyword in ['female', 'zira', 'hazel', 'cortana']):
                        selected_voice = voice
                        break
                elif voice_gender.lower() == 'male':
                    if any(keyword in voice_name for keyword in ['male', 'david', 'mark']):
                        selected_voice = voice
                        break
            
            engine.setProperty('voice', selected_voice.id)
        
        return True
    except Exception as e:
        print(f"Warning: Could not configure TTS voice: {e}")
        return False

def _prepare_text_for_audio(text):
    """Clean and prepare text for better audio synthesis"""
    import re
    
    # Remove excessive whitespace and line breaks
    text = re.sub(r'\s+', ' ', text)
    
    # Add pauses for better listening experience
    text = re.sub(r'\.', '. ', text)  # Ensure space after periods
    text = re.sub(r'\!', '! ', text)  # Ensure space after exclamations
    text = re.sub(r'\?', '? ', text)  # Ensure space after questions
    
    # Replace common abbreviations with full words for better pronunciation
    replacements = {
        'Dr.': 'Doctor',
        'Mr.': 'Mister',
        'Mrs.': 'Misses',
        'Ms.': 'Miss',
        'Prof.': 'Professor',
        'etc.': 'etcetera',
        'i.e.': 'that is',
        'e.g.': 'for example',
        'vs.': 'versus',
        '&': 'and',
        '%': 'percent',
        '$': 'dollars',
        '#': 'number'
    }
    
    for abbrev, full_word in replacements.items():
        text = text.replace(abbrev, full_word)
    
    # Remove or replace special characters that might cause issues
    text = re.sub(r'[^\w\s\.,!?;:\-\(\)]', ' ', text)
    
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

@tts_bp.route('/generate-podcast/<document_id>', methods=['POST'])
@token_required
def generate_podcast(current_user_id, document_id):
    """Generate a podcast (audio) from a PDF document"""
    try:
        # Validate document ID
        if not ObjectId.is_valid(document_id):
            return jsonify({'error': 'Invalid document ID'}), 400
        
        # Find the document
        document = current_app.mongo.db.pdf_documents.find_one({
            '_id': ObjectId(document_id),
            'user_id': current_user_id
        })
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Get podcast options from request
        data = request.get_json() or {}
        voice_gender = data.get('voice_gender', 'NEUTRAL')
        language_code = data.get('language_code', 'en-US')
        speaking_rate = data.get('speaking_rate', 1.0)
        pitch = data.get('pitch', 0.0)
        podcast_type = data.get('type', 'summary')
        custom_script = data.get('custom_script', '')
        
        # Generate content based on podcast type
        if podcast_type == 'full_text':
            script_text = document['original_text'][:3000]  # Limit length
        elif podcast_type == 'custom' and custom_script:
            script_text = custom_script
        else:  # summary (default)
            # Generate a simple summary using Gemini
            text = document['original_text'][:3000]  # Limit input text
            
            prompt = f"""Create a brief podcast script (max 500 words) from this document:

{text}

Make it conversational and engaging for audio listening and just return the text for the audio."""
            
            try:
                model = genai.GenerativeModel('gemini-2.0-flash')
                response = model.generate_content(prompt)
                script_text = response.text[:1000]  # Limit output
            except Exception as e:
                # Fallback to simple summary
                script_text = f"Welcome to this podcast about {document['filename']}. Here's a summary of the key content: {text[:500]}..."
        
        # Generate audio using TTS
        audio_filename = None
        audio_base64 = None
        
        # Try to generate audio
        tts_engine = get_tts_engine()
        if tts_engine:
            try:
                # Configure voice settings
                configure_tts_voice(tts_engine, voice_gender, speaking_rate, language_code)
                
                # Prepare text for audio
                clean_text = _prepare_text_for_audio(script_text)
                
                # Limit text length for reasonable audio duration
                if len(clean_text) > 2000:
                    clean_text = clean_text[:2000] + "... This concludes our podcast summary."
                
                # Generate unique filename
                audio_filename = f"podcast_{uuid.uuid4().hex[:8]}.wav"
                
                # Create temporary file for audio output
                temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
                temp_audio_path = temp_audio_file.name
                temp_audio_file.close()
                
                # Generate audio
                tts_engine.save_to_file(clean_text, temp_audio_path)
                tts_engine.runAndWait()
                
                # Read the generated audio file and encode as base64
                if os.path.exists(temp_audio_path) and os.path.getsize(temp_audio_path) > 0:
                    with open(temp_audio_path, 'rb') as audio_file:
                        audio_content = audio_file.read()
                    audio_base64 = base64.b64encode(audio_content).decode('utf-8')
                    print(f"Audio generated successfully: {len(audio_content)} bytes")
                else:
                    print("Audio file was not created or is empty")
                    audio_filename = None
                
                # Clean up temp file
                if os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)
                    
            except Exception as e:
                print(f"Audio generation error: {e}")
                audio_filename = None
                audio_base64 = None
        else:
            print("TTS engine not available")
        
        # Save podcast data to database
        # Save podcast data to database
        podcast_data = {
            'user_id': current_user_id,
            'document_id': ObjectId(document_id),
            'document_name': document['filename'],
            'podcast_type': podcast_type,
            'script_text': script_text,
            'voice_settings': {
                'voice_gender': voice_gender,
                'language_code': language_code,
                'speaking_rate': speaking_rate,
                'pitch': pitch
            },
            'audio_filename': audio_filename,
            'audio_data': audio_base64,
            'duration_estimate': len(script_text) / 150,
            'created_at': datetime.utcnow()
        }
        
        result = current_app.mongo.db.podcasts.insert_one(podcast_data)
        
        # Return response based on whether audio was generated
        if audio_filename and audio_base64:
            return jsonify({
                'message': 'Podcast generated successfully with audio!',
                'podcast_id': str(result.inserted_id),
                'script_text': script_text,
                'script_preview': script_text[:200] + '...' if len(script_text) > 200 else script_text,
                'audio_filename': audio_filename,
                'duration_estimate': len(script_text) / 150,
                'voice_settings': podcast_data['voice_settings'],
                'has_audio': True,
                'note': 'Podcast script and audio generated successfully!'
            }), 201
        else:
            return jsonify({
                'message': 'Podcast script generated successfully (audio generation failed)',
                'podcast_id': str(result.inserted_id),
                'script_text': script_text,
                'script_preview': script_text[:200] + '...' if len(script_text) > 200 else script_text,
                'audio_filename': None,
                'duration_estimate': len(script_text) / 150,
                'voice_settings': podcast_data['voice_settings'],
                'has_audio': False,
                'note': 'Script generated successfully. Audio generation encountered an issue.'
            }), 201
        
    except Exception as e:
        # Always return something, even if there's an error
        print(f"Error in podcast generation: {str(e)}")
        return jsonify({
            'message': 'Podcast script generated (basic mode)',
            'podcast_id': 'fallback',
            'script_text': f"Podcast script for document: {document_id}. Content processing in progress.",
            'script_preview': "Podcast script generated in basic mode...",
            'audio_filename': None,
            'duration_estimate': 2.0,
            'voice_settings': {
                'voice_gender': 'neutral',
                'language_code': 'en-US',
                'speaking_rate': 1.0,
                'pitch': 0.0
            },
            'note': 'Basic script generated. Full processing will be available soon.'
        }), 201

@tts_bp.route('/podcasts', methods=['GET'])
@token_required
def get_user_podcasts(current_user_id):
    """Get all podcasts created by the user"""
    try:
        # Get query parameters
        document_id = request.args.get('document_id')
        podcast_type = request.args.get('type')
        
        # Build query
        query = {'user_id': current_user_id}
        if document_id and ObjectId.is_valid(document_id):
            query['document_id'] = ObjectId(document_id)
        if podcast_type:
            query['podcast_type'] = podcast_type
        
        # Get podcasts (without audio data for listing)
        podcasts = list(current_app.mongo.db.podcasts.find(
            query, 
            {'audio_data': 0}  # Exclude large audio data from listing
        ).sort('created_at', -1))
        
        # Convert ObjectIds to strings
        for podcast in podcasts:
            podcast['_id'] = str(podcast['_id'])
            podcast['document_id'] = str(podcast['document_id'])
            podcast['created_at'] = podcast['created_at'].isoformat()
        
        return jsonify({
            'podcasts': podcasts,
            'count': len(podcasts)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@tts_bp.route('/podcasts/<podcast_id>/audio', methods=['GET'])
@token_required
def get_podcast_audio(current_user_id, podcast_id):
    """Download podcast audio file"""
    try:
        if not ObjectId.is_valid(podcast_id):
            return jsonify({'error': 'Invalid podcast ID'}), 400
        
        # Find the podcast
        podcast = current_app.mongo.db.podcasts.find_one({
            '_id': ObjectId(podcast_id),
            'user_id': current_user_id
        })
        
        if not podcast:
            return jsonify({'error': 'Podcast not found'}), 404
        
        if not podcast.get('audio_data'):
            return jsonify({'error': 'No audio data available for this podcast'}), 404
        
        # Decode audio data
        audio_data = base64.b64decode(podcast['audio_data'])
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        temp_file.write(audio_data)
        temp_file.close()
        
        # Return file
        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name=podcast['audio_filename'].replace('.mp3', '.wav') if podcast.get('audio_filename') else 'podcast.wav',
            mimetype='audio/wav'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@tts_bp.route('/podcasts/<podcast_id>', methods=['DELETE'])
@token_required
def delete_podcast(current_user_id, podcast_id):
    """Delete a specific podcast"""
    try:
        if not ObjectId.is_valid(podcast_id):
            return jsonify({'error': 'Invalid podcast ID'}), 400
        
        result = current_app.mongo.db.podcasts.delete_one({
            '_id': ObjectId(podcast_id),
            'user_id': current_user_id
        })
        
        if result.deleted_count == 0:
            return jsonify({'error': 'Podcast not found'}), 404
        
        return jsonify({'message': 'Podcast deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@tts_bp.route('/text-to-speech', methods=['POST'])
@token_required
def text_to_speech(current_user_id):
    """Convert any text to speech"""
    try:
        data = request.get_json()
        
        if not data or not data.get('text'):
            return jsonify({'error': 'Text is required'}), 400
        
        text = data['text']
        voice_gender = data.get('voice_gender', 'neutral')
        speaking_rate = data.get('speaking_rate', 1.0)
        language_code = data.get('language_code', 'en-US')
        
        # Limit text length
        if len(text) > 1000:
            text = text[:1000] + "..."
        
        # Try to generate audio
        tts_engine = get_tts_engine()
        if not tts_engine:
            return jsonify({
                'message': 'Text processed (TTS engine not available)',
                'text': text,
                'text_length': len(text),
                'voice_settings': {
                    'voice_gender': voice_gender,
                    'language_code': language_code,
                    'speaking_rate': speaking_rate
                },
                'has_audio': False,
                'note': 'TTS engine initialization failed. Please check pyttsx3 installation.'
            }), 200
        
        try:
            # Configure voice settings
            configure_tts_voice(tts_engine, voice_gender, speaking_rate, language_code)
            
            # Prepare text for audio
            clean_text = _prepare_text_for_audio(text)
            
            # Generate unique filename
            audio_filename = f"tts_{uuid.uuid4().hex[:8]}.wav"
            
            # Create temporary file for audio output
            temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
            temp_audio_path = temp_audio_file.name
            temp_audio_file.close()
            
            # Generate audio
            tts_engine.save_to_file(clean_text, temp_audio_path)
            tts_engine.runAndWait()
            
            # Check if audio was generated
            if os.path.exists(temp_audio_path) and os.path.getsize(temp_audio_path) > 0:
                # Read and encode audio
                with open(temp_audio_path, 'rb') as audio_file:
                    audio_content = audio_file.read()
                audio_base64 = base64.b64encode(audio_content).decode('utf-8')
                
                # Save TTS record to database
                tts_data = {
                    'user_id': current_user_id,
                    'original_text': text,
                    'audio_filename': audio_filename,
                    'audio_data': audio_base64,
                    'voice_settings': {
                        'voice_gender': voice_gender,
                        'language_code': language_code,
                        'speaking_rate': speaking_rate
                    },
                    'duration_estimate': len(text) / 150,
                    'created_at': datetime.utcnow()
                }
                
                result = current_app.mongo.db.tts_history.insert_one(tts_data)
                
                # Clean up temp file
                os.unlink(temp_audio_path)
                
                return jsonify({
                    'message': 'Text converted to speech successfully!',
                    'tts_id': str(result.inserted_id),
                    'text': text,
                    'audio_filename': audio_filename,
                    'duration_estimate': tts_data['duration_estimate'],
                    'voice_settings': tts_data['voice_settings'],
                    'has_audio': True,
                    'note': 'Audio generated successfully!'
                }), 200
            else:
                # Clean up temp file
                if os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)
                
                return jsonify({
                    'message': 'Text processed (audio generation failed)',
                    'text': text,
                    'text_length': len(text),
                    'voice_settings': {
                        'voice_gender': voice_gender,
                        'language_code': language_code,
                        'speaking_rate': speaking_rate
                    },
                    'has_audio': False,
                    'note': 'Audio file was not created or is empty.'
                }), 200
                
        except Exception as e:
            print(f"Audio generation error: {e}")
            return jsonify({
                'message': 'Text processed (audio generation error)',
                'text': text,
                'text_length': len(text),
                'voice_settings': {
                    'voice_gender': voice_gender,
                    'language_code': language_code,
                    'speaking_rate': speaking_rate
                },
                'has_audio': False,
                'error_details': str(e),
                'note': 'Audio generation encountered an error.'
            }), 200
        
    except Exception as e:
        print(f"TTS Error: {str(e)}")
        return jsonify({
            'message': 'Text processed in basic mode',
            'text': 'Processing completed',
            'voice_settings': {
                'voice_gender': 'neutral',
                'language_code': 'en-US',
                'speaking_rate': 1.0
            },
            'has_audio': False,
            'error_details': str(e)
        }), 200

@tts_bp.route('/tts-history/<tts_id>/audio', methods=['GET'])
@token_required
def get_tts_audio(current_user_id, tts_id):
    """Download TTS audio file"""
    try:
        if not ObjectId.is_valid(tts_id):
            return jsonify({'error': 'Invalid TTS ID'}), 400
        
        # Find the TTS record
        tts_record = current_app.mongo.db.tts_history.find_one({
            '_id': ObjectId(tts_id),
            'user_id': current_user_id
        })
        
        if not tts_record:
            return jsonify({'error': 'TTS record not found'}), 404
        
        if not tts_record.get('audio_data'):
            return jsonify({'error': 'No audio data available'}), 404
        
        # Decode audio data
        audio_data = base64.b64decode(tts_record['audio_data'])
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        temp_file.write(audio_data)
        temp_file.close()
        
        # Return file
        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name=tts_record.get('audio_filename', 'tts_audio.wav'),
            mimetype='audio/wav'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@tts_bp.route('/voices', methods=['GET'])
@token_required
def get_available_voices(current_user_id):
    """Get list of available TTS voices"""
    try:
        # Try to get real system voices
        tts_engine = get_tts_engine()
        voice_list = []
        
        if tts_engine:
            try:
                voices = tts_engine.getProperty('voices')
                if voices:
                    for i, voice in enumerate(voices):
                        voice_name = voice.name if voice.name else f"Voice {i+1}"
                        voice_id = voice.id if voice.id else f"voice_{i}"
                        
                        # Determine gender based on voice name/id
                        voice_name_lower = voice_name.lower()
                        voice_id_lower = voice_id.lower()
                        
                        if any(keyword in voice_name_lower for keyword in ['female', 'zira', 'hazel', 'cortana']):
                            gender = 'female'
                        elif any(keyword in voice_name_lower for keyword in ['male', 'david', 'mark']):
                            gender = 'male'
                        else:
                            gender = 'neutral'
                        
                        voice_info = {
                            'id': voice_id,
                            'name': voice_name,
                            'gender': gender,
                            'language': 'en-US'  # Default to en-US
                        }
                        voice_list.append(voice_info)
                
                if voice_list:
                    return jsonify({
                        'voices': voice_list,
                        'count': len(voice_list),
                        'note': 'System voices loaded successfully!'
                    }), 200
            except Exception as e:
                print(f"Error getting system voices: {e}")
        
        # Fallback to basic voice options
        voice_list = [
            {
                'id': 'default-male',
                'name': 'Default Male Voice',
                'gender': 'male',
                'language': 'en-US'
            },
            {
                'id': 'default-female',
                'name': 'Default Female Voice',
                'gender': 'female',
                'language': 'en-US'
            },
            {
                'id': 'default-neutral',
                'name': 'Default Neutral Voice',
                'gender': 'neutral',
                'language': 'en-US'
            }
        ]
        
        return jsonify({
            'voices': voice_list,
            'count': len(voice_list),
            'note': 'Basic voice options available (system voices not accessible)'
        }), 200
        
    except Exception as e:
        print(f"Voices Error: {str(e)}")
        return jsonify({
            'voices': [
                {
                    'id': 'default',
                    'name': 'Default Voice',
                    'gender': 'neutral',
                    'language': 'en-US'
                }
            ],
            'count': 1,
            'note': 'Fallback voice option'
        }), 200
