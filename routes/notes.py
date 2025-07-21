from flask import Blueprint, request, jsonify, current_app
from routes.auth import token_required
from datetime import datetime
import google.generativeai as genai
import os
from bson import ObjectId

notes_bp = Blueprint('notes', __name__)

# Configure Gemini API
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

@notes_bp.route('/', methods=['GET'])
@token_required
def get_notes(current_user_id):
    try:
        notes = list(current_app.mongo.db.notes.find({'user_id': current_user_id}).sort('created_at', -1))
        
        # Convert ObjectId to string
        for note in notes:
            note['_id'] = str(note['_id'])
            note['created_at'] = note['created_at'].isoformat()
            note['updated_at'] = note['updated_at'].isoformat()
        
        return jsonify({'notes': notes}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@notes_bp.route('/', methods=['POST'])
@token_required
def create_note(current_user_id):
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('title') or not data.get('content'):
            return jsonify({'error': 'Title and content are required'}), 400
        
        note_data = {
            'user_id': current_user_id,
            'title': data['title'],
            'content': data['content'],
            'summary': data.get('summary', ''),
            'tags': data.get('tags', []),
            'category': data.get('category', 'general'),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = current_app.mongo.db.notes.insert_one(note_data)
        note_data['_id'] = str(result.inserted_id)
        note_data['created_at'] = note_data['created_at'].isoformat()
        note_data['updated_at'] = note_data['updated_at'].isoformat()
        
        return jsonify({
            'message': 'Note created successfully',
            'note': note_data
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@notes_bp.route('/summarize', methods=['POST'])
@token_required
def summarize_note(current_user_id):
    try:
        data = request.get_json()
        
        if not data.get('content'):
            return jsonify({'error': 'Content is required for summarization'}), 400
        
        content = data['content']
        summary_type = data.get('type', 'concise')  # concise, detailed, bullet_points
        
        # Create appropriate prompt based on summary type
        if summary_type == 'bullet_points':
            prompt = f"""Please summarize the following text in bullet points. Focus on the key concepts and main ideas:

{content}

Summary in bullet points:"""
        elif summary_type == 'detailed':
            prompt = f"""Please provide a detailed summary of the following text, maintaining important details and context:

{content}

Detailed summary:"""
        else:  # concise
            prompt = f"""Please provide a concise summary of the following text, capturing the main ideas in 2-3 sentences:

{content}

Concise summary:"""
        
        # Use Gemini API to generate summary
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        summary = response.text.strip()
        
        # Save the note with summary if title is provided
        if data.get('title'):
            note_data = {
                'user_id': current_user_id,
                'title': data['title'],
                'content': content,
                'summary': summary,
                'summary_type': summary_type,
                'tags': data.get('tags', []),
                'category': data.get('category', 'summarized'),
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            result = current_app.mongo.db.notes.insert_one(note_data)
            note_data['_id'] = str(result.inserted_id)
            note_data['created_at'] = note_data['created_at'].isoformat()
            note_data['updated_at'] = note_data['updated_at'].isoformat()
            
            return jsonify({
                'message': 'Note summarized and saved successfully',
                'summary': summary,
                'note': note_data
            }), 201
        else:
            return jsonify({
                'summary': summary
            }), 200
        
    except Exception as e:
        return jsonify({'error': f'Summarization failed: {str(e)}'}), 500

@notes_bp.route('/generate-glossary', methods=['POST'])
@token_required
def generate_glossary(current_user_id):
    try:
        data = request.get_json()
        
        if not data.get('content'):
            return jsonify({'error': 'Content is required for glossary generation'}), 400
        
        content = data['content']
        subject = data.get('subject', 'general')
        
        prompt = f"""Please extract key terms and concepts from the following {subject} text and create a glossary. Format each entry as "Term: Definition".

Text:
{content}

Glossary:"""
        
        # Use Gemini API to generate glossary
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        glossary = response.text.strip()
        
        # Parse glossary into structured format
        glossary_items = []
        for line in glossary.split('\n'):
            if ':' in line and line.strip():
                term, definition = line.split(':', 1)
                glossary_items.append({
                    'term': term.strip(),
                    'definition': definition.strip()
                })
        
        # Save glossary if title is provided
        if data.get('title'):
            glossary_data = {
                'user_id': current_user_id,
                'title': data['title'],
                'content': content,
                'glossary': glossary_items,
                'subject': subject,
                'category': 'glossary',
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            result = current_app.mongo.db.notes.insert_one(glossary_data)
            glossary_data['_id'] = str(result.inserted_id)
            glossary_data['created_at'] = glossary_data['created_at'].isoformat()
            glossary_data['updated_at'] = glossary_data['updated_at'].isoformat()
            
            return jsonify({
                'message': 'Glossary generated and saved successfully',
                'glossary': glossary_items,
                'note': glossary_data
            }), 201
        else:
            return jsonify({
                'glossary': glossary_items
            }), 200
        
    except Exception as e:
        return jsonify({'error': f'Glossary generation failed: {str(e)}'}), 500

@notes_bp.route('/generate-flashcards', methods=['POST'])
@token_required
def generate_flashcards(current_user_id):
    try:
        data = request.get_json()
        
        if not data.get('content'):
            return jsonify({'error': 'Content is required for flashcard generation'}), 400
        
        content = data['content']
        num_cards = data.get('num_cards', 10)
        difficulty = data.get('difficulty', 'medium')  # easy, medium, hard
        
        prompt = f"""Create {num_cards} flashcards from the following content. Make them {difficulty} difficulty level. Format as "Q: [Question] | A: [Answer]" with each flashcard on a new line.

Content:
{content}

Flashcards:"""
        
        # Use Gemini API to generate flashcards
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        flashcards_text = response.text.strip()
        
        # Parse flashcards into structured format
        flashcards = []
        for line in flashcards_text.split('\n'):
            if '|' in line and line.strip():
                parts = line.split('|')
                if len(parts) >= 2:
                    question = parts[0].replace('Q:', '').strip()
                    answer = parts[1].replace('A:', '').strip()
                    flashcards.append({
                        'question': question,
                        'answer': answer,
                        'difficulty': difficulty
                    })
        
        # Save flashcards if title is provided
        if data.get('title'):
            flashcards_data = {
                'user_id': current_user_id,
                'title': data['title'],
                'content': content,
                'flashcards': flashcards,
                'difficulty': difficulty,
                'category': 'flashcards',
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            result = current_app.mongo.db.notes.insert_one(flashcards_data)
            flashcards_data['_id'] = str(result.inserted_id)
            flashcards_data['created_at'] = flashcards_data['created_at'].isoformat()
            flashcards_data['updated_at'] = flashcards_data['updated_at'].isoformat()
            
            return jsonify({
                'message': 'Flashcards generated and saved successfully',
                'flashcards': flashcards,
                'note': flashcards_data
            }), 201
        else:
            return jsonify({
                'flashcards': flashcards
            }), 200
        
    except Exception as e:
        return jsonify({'error': f'Flashcard generation failed: {str(e)}'}), 500

@notes_bp.route('/<note_id>', methods=['PUT'])
@token_required
def update_note(current_user_id, note_id):
    try:
        data = request.get_json()
        
        update_data = {'updated_at': datetime.utcnow()}
        
        allowed_fields = ['title', 'content', 'summary', 'tags', 'category']
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        result = current_app.mongo.db.notes.update_one(
            {'_id': ObjectId(note_id), 'user_id': current_user_id},
            {'$set': update_data}
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Note not found'}), 404
        
        return jsonify({'message': 'Note updated successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@notes_bp.route('/<note_id>', methods=['DELETE'])
@token_required
def delete_note(current_user_id, note_id):
    try:
        result = current_app.mongo.db.notes.delete_one(
            {'_id': ObjectId(note_id), 'user_id': current_user_id}
        )
        
        if result.deleted_count == 0:
            return jsonify({'error': 'Note not found'}), 404
        
        return jsonify({'message': 'Note deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
