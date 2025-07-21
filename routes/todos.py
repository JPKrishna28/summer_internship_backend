from flask import Blueprint, request, jsonify, current_app
from routes.auth import token_required
from datetime import datetime
from bson import ObjectId

todos_bp = Blueprint('todos', __name__)

@todos_bp.route('/', methods=['GET'])
@token_required
def get_todos(current_user_id):
    try:
        # Get query parameters for filtering
        status = request.args.get('status')  # all, completed, pending
        tag = request.args.get('tag')
        due_date = request.args.get('due_date')
        
        # Build query
        query = {'user_id': current_user_id}
        
        if status == 'completed':
            query['completed'] = True
        elif status == 'pending':
            query['completed'] = False
            
        if tag:
            query['tags'] = {'$in': [tag]}
            
        if due_date:
            query['due_date'] = {'$lte': datetime.fromisoformat(due_date)}
        
        todos = list(current_app.mongo.db.todos.find(query).sort('created_at', -1))
        
        # Convert ObjectId to string
        for todo in todos:
            todo['_id'] = str(todo['_id'])
            if todo.get('due_date'):
                todo['due_date'] = todo['due_date'].isoformat()
            todo['created_at'] = todo['created_at'].isoformat()
            todo['updated_at'] = todo['updated_at'].isoformat()
        
        return jsonify({'todos': todos}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@todos_bp.route('/', methods=['POST'])
@token_required
def create_todo(current_user_id):
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('title'):
            return jsonify({'error': 'Title is required'}), 400
        
        todo_data = {
            'user_id': current_user_id,
            'title': data['title'],
            'description': data.get('description', ''),
            'completed': False,
            'priority': data.get('priority', 'medium'),  # low, medium, high
            'tags': data.get('tags', []),
            'due_date': datetime.fromisoformat(data['due_date']) if data.get('due_date') else None,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = current_app.mongo.db.todos.insert_one(todo_data)
        todo_data['_id'] = str(result.inserted_id)
        
        # Convert datetime objects to ISO format for JSON response
        if todo_data.get('due_date'):
            todo_data['due_date'] = todo_data['due_date'].isoformat()
        todo_data['created_at'] = todo_data['created_at'].isoformat()
        todo_data['updated_at'] = todo_data['updated_at'].isoformat()
        
        return jsonify({
            'message': 'Todo created successfully',
            'todo': todo_data
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@todos_bp.route('/<todo_id>', methods=['PUT'])
@token_required
def update_todo(current_user_id, todo_id):
    try:
        data = request.get_json()
        
        # Build update data
        update_data = {'updated_at': datetime.utcnow()}
        
        if 'title' in data:
            update_data['title'] = data['title']
        if 'description' in data:
            update_data['description'] = data['description']
        if 'completed' in data:
            update_data['completed'] = data['completed']
        if 'priority' in data:
            update_data['priority'] = data['priority']
        if 'tags' in data:
            update_data['tags'] = data['tags']
        if 'due_date' in data:
            update_data['due_date'] = datetime.fromisoformat(data['due_date']) if data['due_date'] else None
        
        result = current_app.mongo.db.todos.update_one(
            {'_id': ObjectId(todo_id), 'user_id': current_user_id},
            {'$set': update_data}
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Todo not found'}), 404
        
        return jsonify({'message': 'Todo updated successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@todos_bp.route('/<todo_id>', methods=['DELETE'])
@token_required
def delete_todo(current_user_id, todo_id):
    try:
        result = current_app.mongo.db.todos.delete_one(
            {'_id': ObjectId(todo_id), 'user_id': current_user_id}
        )
        
        if result.deleted_count == 0:
            return jsonify({'error': 'Todo not found'}), 404
        
        return jsonify({'message': 'Todo deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@todos_bp.route('/stats', methods=['GET'])
@token_required
def get_todo_stats(current_user_id):
    try:
        pipeline = [
            {'$match': {'user_id': current_user_id}},
            {'$group': {
                '_id': None,
                'total': {'$sum': 1},
                'completed': {'$sum': {'$cond': ['$completed', 1, 0]}},
                'pending': {'$sum': {'$cond': ['$completed', 0, 1]}},
                'overdue': {'$sum': {
                    '$cond': [
                        {'$and': [
                            {'$ne': ['$due_date', None]},
                            {'$lt': ['$due_date', datetime.utcnow()]},
                            {'$eq': ['$completed', False]}
                        ]}, 1, 0
                    ]
                }}
            }}
        ]
        
        result = list(current_app.mongo.db.todos.aggregate(pipeline))
        stats = result[0] if result else {
            'total': 0, 'completed': 0, 'pending': 0, 'overdue': 0
        }
        
        # Remove the _id field
        stats.pop('_id', None)
        
        return jsonify({'stats': stats}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
