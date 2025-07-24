from flask import Blueprint, request, jsonify, current_app, send_file
from routes.auth import token_required
from datetime import datetime
import google.generativeai as genai
import os
import fitz  # PyMuPDF
import faiss
import numpy as np
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from sklearn.feature_extraction.text import TfidfVectorizer
import tempfile
import json
import base64
import uuid
from bson import ObjectId

pdf_qa_bp = Blueprint('pdf_qa', __name__)

# Configure Gemini API
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# Initialize embeddings model (using a lightweight model for CPU)
embeddings_model = None

def get_embeddings_model():
    global embeddings_model
    if embeddings_model is None:
        try:
            # Use a lightweight embedding model that works well with CPU
            embeddings_model = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={'device': 'cpu'}
            )
        except Exception as e:
            # Fallback to TF-IDF if sentence transformers not available
            print(f"Warning: Could not load sentence transformers: {e}")
            embeddings_model = TfidfVectorizer(max_features=384, stop_words='english')
    return embeddings_model

@pdf_qa_bp.route('/upload', methods=['POST'])
@token_required
def upload_pdf(current_user_id):
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are allowed'}), 400
        
        # Save file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            file.save(temp_file.name)
            temp_path = temp_file.name
        
        try:
            # Extract text from PDF
            doc = fitz.open(temp_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            
            if not text.strip():
                return jsonify({'error': 'No text found in PDF'}), 400
            
            # Split text into chunks
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                length_function=len
            )
            chunks = text_splitter.split_text(text)
            
            # Create embeddings
            embeddings_model = get_embeddings_model()
            
            if hasattr(embeddings_model, 'embed_documents'):
                # Using sentence transformers
                embeddings = embeddings_model.embed_documents(chunks)
                embeddings_array = np.array(embeddings).astype('float32')
            else:
                # Using TF-IDF as fallback
                embeddings_array = embeddings_model.fit_transform(chunks).toarray().astype('float32')
            
            # Create FAISS index
            dimension = embeddings_array.shape[1]
            index = faiss.IndexFlatL2(dimension)
            index.add(embeddings_array)
            
            # Save to database
            pdf_data = {
                'user_id': current_user_id,
                'filename': file.filename,
                'original_text': text,
                'chunks': chunks,
                'embeddings': embeddings_array.tolist(),  # Store as list for MongoDB
                'num_chunks': len(chunks),
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            result = current_app.mongo.db.pdf_documents.insert_one(pdf_data)
            
            return jsonify({
                'message': 'PDF uploaded and processed successfully',
                'document_id': str(result.inserted_id),
                'filename': file.filename,
                'num_chunks': len(chunks),
                'text_preview': text[:500] + '...' if len(text) > 500 else text
            }), 201
            
        finally:
            # Clean up temp file
            os.unlink(temp_path)
        
    except Exception as e:
        return jsonify({'error': f'PDF processing failed: {str(e)}'}), 500

@pdf_qa_bp.route('/documents', methods=['GET'])
@token_required
def get_documents(current_user_id):
    try:
        documents = list(current_app.mongo.db.pdf_documents.find(
            {'user_id': current_user_id},
            {'embeddings': 0, 'chunks': 0, 'original_text': 0}  # Exclude large fields
        ).sort('created_at', -1))
        
        # Convert ObjectId to string
        for doc in documents:
            doc['_id'] = str(doc['_id'])
            doc['created_at'] = doc['created_at'].isoformat()
            doc['updated_at'] = doc['updated_at'].isoformat()
        
        return jsonify({'documents': documents}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pdf_qa_bp.route('/ask', methods=['POST'])
@token_required
def ask_question(current_user_id):
    try:
        data = request.get_json()
        
        if not data.get('question'):
            return jsonify({'error': 'Question is required'}), 400
        
        if not data.get('document_id'):
            return jsonify({'error': 'Document ID is required'}), 400
        
        question = data['question']
        document_id = data['document_id']
        
        # Get document from database
        document = current_app.mongo.db.pdf_documents.find_one({
            '_id': ObjectId(document_id),
            'user_id': current_user_id
        })
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Get relevant chunks using similarity search
        embeddings_model = get_embeddings_model()
        
        if hasattr(embeddings_model, 'embed_query'):
            # Using sentence transformers
            question_embedding = embeddings_model.embed_query(question)
            question_vector = np.array([question_embedding]).astype('float32')
        else:
            # Using TF-IDF as fallback
            question_vector = embeddings_model.transform([question]).toarray().astype('float32')
        
        # Create FAISS index from stored embeddings
        embeddings_array = np.array(document['embeddings']).astype('float32')
        dimension = embeddings_array.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings_array)
        
        # Search for similar chunks
        k = min(5, len(document['chunks']))  # Get top 5 relevant chunks
        distances, indices = index.search(question_vector, k)
        
        # Get relevant text chunks
        relevant_chunks = [document['chunks'][i] for i in indices[0]]
        context = '\n\n'.join(relevant_chunks)
        
        # Generate answer using Gemini
        prompt = f"""Based on the following context from a document, please answer the question. If the answer cannot be found in the context, please say so.

Context:
{context}

Question: {question}

Answer:"""
        
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        answer = response.text.strip()
        
        # Save Q&A to database
        qa_data = {
            'user_id': current_user_id,
            'document_id': document_id,
            'question': question,
            'answer': answer,
            'context_chunks': relevant_chunks,
            'similarity_scores': distances[0].tolist(),
            'created_at': datetime.utcnow()
        }
        
        current_app.mongo.db.pdf_qa_history.insert_one(qa_data)
        
        return jsonify({
            'answer': answer,
            'context_used': len(relevant_chunks),
            'confidence_scores': distances[0].tolist()
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Question answering failed: {str(e)}'}), 500

@pdf_qa_bp.route('/history', methods=['GET'])
@token_required
def get_qa_history(current_user_id):
    try:
        document_id = request.args.get('document_id')
        
        query = {'user_id': current_user_id}
        if document_id:
            query['document_id'] = document_id
        
        history = list(current_app.mongo.db.pdf_qa_history.find(
            query,
            {'context_chunks': 0}  # Exclude context chunks to reduce response size
        ).sort('created_at', -1).limit(50))
        
        # Convert ObjectId to string
        for item in history:
            item['_id'] = str(item['_id'])
            item['created_at'] = item['created_at'].isoformat()
        
        return jsonify({'history': history}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pdf_qa_bp.route('/documents/<document_id>', methods=['DELETE'])
@token_required
def delete_document(current_user_id, document_id):
    try:
        # Delete document
        doc_result = current_app.mongo.db.pdf_documents.delete_one({
            '_id': ObjectId(document_id),
            'user_id': current_user_id
        })
        
        if doc_result.deleted_count == 0:
            return jsonify({'error': 'Document not found'}), 404
        
        # Delete associated Q&A history
        current_app.mongo.db.pdf_qa_history.delete_many({
            'document_id': document_id,
            'user_id': current_user_id
        })
        
        return jsonify({'message': 'Document and associated history deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pdf_qa_bp.route('/generate-questions', methods=['POST'])
@token_required
def generate_questions(current_user_id):
    try:
        data = request.get_json()
        
        if not data.get('document_id'):
            return jsonify({'error': 'Document ID is required'}), 400
        
        document_id = data['document_id']
        num_questions = data.get('num_questions', 5)
        question_type = data.get('type', 'mixed')  # mcq, short_answer, essay, mixed
        
        # Get document from database
        document = current_app.mongo.db.pdf_documents.find_one({
            '_id': ObjectId(document_id),
            'user_id': current_user_id
        })
        
        if not document:
            return jsonify({'error': 'Document not found'}), 404
        
        # Use a sample of the text for question generation
        text_sample = document['original_text'][:3000]  # First 3000 characters
        
        if question_type == 'mcq':
            prompt = f"""Generate {num_questions} multiple choice questions based on the following text. Format each question as:
Q: [Question]
A) [Option A]
B) [Option B] 
C) [Option C]
D) [Option D]
Correct: [Letter]

Text:
{text_sample}

Questions:"""
        elif question_type == 'short_answer':
            prompt = f"""Generate {num_questions} short answer questions based on the following text. Each question should be answerable in 2-3 sentences.

Text:
{text_sample}

Questions:"""
        elif question_type == 'essay':
            prompt = f"""Generate {num_questions} essay questions based on the following text. Each question should require analytical thinking and detailed responses.

Text:
{text_sample}

Questions:"""
        else:  # mixed
            prompt = f"""Generate {num_questions} questions of mixed types (multiple choice, short answer, and essay) based on the following text.

Text:
{text_sample}

Questions:"""
        
        # Generate questions using Gemini
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        questions_text = response.text.strip()
        
        # Save generated questions
        questions_data = {
            'user_id': current_user_id,
            'document_id': document_id,
            'questions_text': questions_text,
            'question_type': question_type,
            'num_questions': num_questions,
            'created_at': datetime.utcnow()
        }
        
        result = current_app.mongo.db.generated_questions.insert_one(questions_data)
        
        return jsonify({
            'message': 'Questions generated successfully',
            'questions': questions_text,
            'questions_id': str(result.inserted_id)
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Question generation failed: {str(e)}'}), 500

@pdf_qa_bp.route('/summarize/<document_id>', methods=['POST'])
@token_required
def summarize_document(current_user_id, document_id):
    """Generate a comprehensive summary of a PDF document for study purposes"""
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
        
        # Get summarization options from request
        data = request.get_json() or {}
        summary_type = data.get('type', 'comprehensive')  # comprehensive, brief, bullet_points, key_concepts
        focus_area = data.get('focus_area', '')  # Optional: specific topic to focus on
        
        # Get the document text
        text = document['original_text']
        
        # Create appropriate prompt based on summary type
        if summary_type == 'brief':
            prompt = f"""Please provide a brief summary of the following document in 3-4 sentences. Focus on the main topic and key takeaways:

{text}

Brief Summary:"""
        
        elif summary_type == 'bullet_points':
            prompt = f"""Please summarize the following document in bullet points. Organize the information in a clear, hierarchical structure suitable for studying:

{text}

Summary in bullet points:"""
        
        elif summary_type == 'key_concepts':
            prompt = f"""Please extract and explain the key concepts, definitions, and important terms from the following document. Format it as a study guide:

{text}

Key Concepts and Definitions:"""
        
        elif summary_type == 'exam_prep':
            prompt = f"""Please create an exam preparation summary of the following document. Include:
1. Main topics and subtopics
2. Key facts and figures
3. Important concepts to remember
4. Potential exam questions

{text}

Exam Preparation Summary:"""
        
        else:  # comprehensive
            prompt = f"""Please provide a comprehensive summary of the following document. Include:
1. Main topic and purpose
2. Key points and arguments
3. Important details and examples
4. Conclusions and implications

Make it suitable for a student studying for exams.

{text}

Comprehensive Summary:"""
        
        # Add focus area if specified
        if focus_area:
            prompt += f"\n\nPlease pay special attention to information related to: {focus_area}"
        
        # Generate summary using Gemini
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        summary_text = response.text
        
        # Save summary to database
        summary_data = {
            'user_id': current_user_id,
            'document_id': ObjectId(document_id),
            'document_name': document['filename'],
            'summary_type': summary_type,
            'focus_area': focus_area,
            'summary_text': summary_text,
            'created_at': datetime.utcnow()
        }
        
        result = current_app.mongo.db.document_summaries.insert_one(summary_data)
        
        return jsonify({
            'message': 'Document summary generated successfully',
            'summary': summary_text,
            'summary_type': summary_type,
            'summary_id': str(result.inserted_id),
            'document_name': document['filename']
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Summary generation failed: {str(e)}'}), 500

@pdf_qa_bp.route('/summaries', methods=['GET'])
@token_required
def get_user_summaries(current_user_id):
    """Get all summaries created by the user"""
    try:
        # Get query parameters
        document_id = request.args.get('document_id')
        summary_type = request.args.get('type')
        
        # Build query
        query = {'user_id': current_user_id}
        if document_id and ObjectId.is_valid(document_id):
            query['document_id'] = ObjectId(document_id)
        if summary_type:
            query['summary_type'] = summary_type
        
        # Get summaries
        summaries = list(current_app.mongo.db.document_summaries.find(query).sort('created_at', -1))
        
        # Convert ObjectIds to strings
        for summary in summaries:
            summary['_id'] = str(summary['_id'])
            summary['document_id'] = str(summary['document_id'])
            summary['created_at'] = summary['created_at'].isoformat()
        
        return jsonify({
            'summaries': summaries,
            'count': len(summaries)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pdf_qa_bp.route('/summaries/<summary_id>', methods=['DELETE'])
@token_required
def delete_summary(current_user_id, summary_id):
    """Delete a specific summary"""
    try:
        if not ObjectId.is_valid(summary_id):
            return jsonify({'error': 'Invalid summary ID'}), 400
        
        result = current_app.mongo.db.document_summaries.delete_one({
            '_id': ObjectId(summary_id),
            'user_id': current_user_id
        })
        
        if result.deleted_count == 0:
            return jsonify({'error': 'Summary not found'}), 404
        
        return jsonify({'message': 'Summary deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
