# AI Productivity Suite - Backend

A Flask-based REST API server that powers the AI Productivity Suite for Students. This backend provides authentication, task management, habit tracking, note summarization, PDF Q&A, and Pomodoro timer functionality with AI integration using Google Gemini API.

## 🚀 Features

- **Authentication & Authorization** - JWT-based user authentication
- **Task Management** - CRUD operations for todos with filtering and tagging
- **Habit Tracking** - Daily habit monitoring with progress analytics
- **AI Note Summarization** - Intelligent text summarization using Google Gemini
- **PDF Q&A System** - RAG-based document question answering with LangChain + FAISS
- **Pomodoro Timer** - Session tracking with statistics and settings
- **CORS Support** - Configured for frontend integration

## 🛠️ Tech Stack

- **Framework**: Flask 2.3.3
- **Database**: MongoDB with PyMongo
- **AI Integration**: Google Gemini API
- **RAG System**: LangChain + FAISS for vector search
- **Authentication**: JWT with bcrypt password hashing
- **PDF Processing**: PyMuPDF + pdfplumber
- **Environment**: python-dotenv for configuration

## 📋 Prerequisites

- Python 3.8 or higher
- MongoDB (local or cloud instance)
- Google Gemini API key

## 🔧 Installation

1. **Clone the repository and navigate to backend**
   ```bash
   cd backend
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` file with your configuration:
   ```bash
   SECRET_KEY=your-secret-key-here
   MONGO_URI=mongodb://localhost:27017/ai_productivity_suite
   GEMINI_API_KEY=your-gemini-api-key
   FRONTEND_URL=http://localhost:3000
   ```

5. **Start MongoDB** (if running locally)
   ```bash
   mongod
   ```

## 🚀 Running the Server

### Development Mode
```bash
python app.py
```
Server will start on `http://localhost:5000`

### Using the batch file
```bash
../start_backend.bat
```

## 📚 API Documentation

### Base URL
```
http://localhost:5000/api
```

### Authentication Endpoints
- `POST /auth/register` - User registration
- `POST /auth/login` - User login
- `GET /auth/me` - Get current user info

### Todo Endpoints
- `GET /todos` - Get todos (supports filtering by status, tag, due_date)
- `POST /todos` - Create new todo
- `GET /todos/{id}` - Get specific todo
- `PUT /todos/{id}` - Update todo
- `DELETE /todos/{id}` - Delete todo

### Habits Endpoints
- `GET /habits` - Get user habits
- `POST /habits` - Create new habit
- `PUT /habits/{id}` - Update habit
- `DELETE /habits/{id}` - Delete habit
- `POST /habits/{id}/log` - Log habit completion

### Notes Endpoints
- `GET /notes` - Get notes (supports filtering and search)
- `POST /notes` - Create new note
- `PUT /notes/{id}` - Update note
- `DELETE /notes/{id}` - Delete note
- `POST /notes/summarize` - AI-powered text summarization

### PDF Q&A Endpoints
- `POST /pdf-qa/upload` - Upload PDF for processing
- `GET /pdf-qa/documents` - Get uploaded documents
- `POST /pdf-qa/query` - Ask questions about uploaded PDFs
- `DELETE /pdf-qa/documents/{id}` - Delete document

### Pomodoro Endpoints
- `GET /pomodoro/settings` - Get timer settings
- `PUT /pomodoro/settings` - Update timer settings
- `POST /pomodoro/sessions` - Start new session
- `GET /pomodoro/sessions` - Get session history
- `PUT /pomodoro/sessions/{id}/complete` - Complete session
- `DELETE /pomodoro/sessions/{id}` - Cancel session
- `GET /pomodoro/stats` - Get productivity statistics

### Utility Endpoints
- `GET /health` - Health check
- `GET /test` - CORS test endpoint

## 🗂️ Project Structure

```
backend/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
├── .env                  # Environment variables (create from example)
├── routes/               # API route blueprints
│   ├── auth.py          # Authentication routes
│   ├── todos.py         # Todo management routes
│   ├── habits.py        # Habit tracking routes
│   ├── notes.py         # Notes and summarization routes
│   ├── pdf_qa.py        # PDF Q&A routes
│   └── pomodoro.py      # Pomodoro timer routes
└── README.md            # This file
```

## 🔐 Authentication

All API endpoints (except auth and utility endpoints) require JWT authentication. Include the token in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

## 🧪 Testing

### Health Check
```bash
curl http://localhost:5000/api/health
```

### CORS Test
```bash
curl http://localhost:5000/api/test
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key for sessions | Required |
| `MONGO_URI` | MongoDB connection string | `mongodb://localhost:27017/ai_productivity_suite` |
| `GEMINI_API_KEY` | Google Gemini API key | Required |
| `FRONTEND_URL` | Frontend URL for CORS | `http://localhost:3000` |
| `FLASK_ENV` | Flask environment | `development` |

### MongoDB Collections

- `users` - User accounts and profiles
- `todos` - Task management data
- `habits` - Habit tracking information
- `notes` - User notes and summaries
- `pdf_documents` - Uploaded PDF metadata
- `pdf_embeddings` - Vector embeddings for RAG
- `pomodoro_sessions` - Timer session history
- `pomodoro_settings` - User timer preferences

## 🤖 AI Features

### Google Gemini Integration
- Text summarization with multiple styles (concise, detailed, bullet points)
- Intelligent content generation and analysis

### RAG System (PDF Q&A)
- Document embedding using FAISS vector database
- Context-aware question answering over uploaded PDFs
- Semantic search and retrieval

## 🐛 Troubleshooting

### Common Issues

1. **CORS Errors**
   - Ensure `FRONTEND_URL` is set correctly in `.env`
   - Check that frontend is running on the specified URL

2. **MongoDB Connection Issues**
   - Verify MongoDB is running
   - Check `MONGO_URI` in `.env` file
   - Ensure database permissions are correct

3. **AI API Errors**
   - Verify `GEMINI_API_KEY` is valid and has proper permissions
   - Check API rate limits and quotas

4. **Missing Dependencies**
   - Run `pip install -r requirements.txt`
   - Ensure virtual environment is activated

### Logs
Monitor the console output for detailed error messages and request logs.

## 🚀 Deployment

For production deployment:

1. Set `FLASK_ENV=production` in environment
2. Use a production WSGI server like Gunicorn
3. Configure MongoDB for production use
4. Set up proper SSL/TLS certificates
5. Configure environment variables securely

## 📄 License

This project is part of the AI Productivity Suite for Students.

## 🤝 Contributing

1. Ensure code follows PEP 8 standards
2. Add appropriate error handling and validation
3. Include proper authentication checks
4. Test API endpoints thoroughly
5. Update documentation for new features
"# summer_internship_backend" 
