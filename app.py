from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
from flask_pymongo import PyMongo
from dotenv import load_dotenv
import os
from datetime import datetime

# Import blueprints
from routes.auth import auth_bp
from routes.todos import todos_bp
from routes.habits import habits_bp
from routes.notes import notes_bp
from routes.pdf_qa import pdf_qa_bp
from routes.pomodoro import pomodoro_bp
from routes.tts import tts_bp

# Load environment variables
load_dotenv()

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['MONGO_URI'] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/ai_productivity_suite')
    
    # Disable automatic trailing slash redirects (this causes CORS issues)
    app.url_map.strict_slashes = False
    
    # Initialize extensions with explicit CORS configuration
    CORS(app, 
         origins=['http://localhost:3000', 'http://127.0.0.1:3000'],
         methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
         allow_headers=['Content-Type', 'Authorization'],
         supports_credentials=True)
    
    mongo = PyMongo(app)
    
    # Make mongo available to blueprints
    app.mongo = mongo
    
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(todos_bp, url_prefix='/api/todos')
    app.register_blueprint(habits_bp, url_prefix='/api/habits')
    app.register_blueprint(notes_bp, url_prefix='/api/notes')
    app.register_blueprint(pdf_qa_bp, url_prefix='/api/pdf-qa')
    app.register_blueprint(pomodoro_bp, url_prefix='/api/pomodoro')
    app.register_blueprint(tts_bp, url_prefix='/api/tts')
    
    # Health check endpoint
    @app.route('/api/health')
    def health_check():
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0.0'
        })
    
    # Test endpoint without authentication
    @app.route('/api/test')
    def test_endpoint():
        return jsonify({
            'message': 'Test endpoint working',
            'cors': 'enabled'
        })
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
