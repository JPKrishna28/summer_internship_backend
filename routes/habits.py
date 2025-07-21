from flask import Blueprint, request, jsonify, current_app
from routes.auth import token_required
from datetime import datetime, timedelta
from bson import ObjectId

habits_bp = Blueprint('habits', __name__)

@habits_bp.route('/', methods=['GET'])
@token_required
def get_habits(current_user_id):
    try:
        habits = list(current_app.mongo.db.habits.find({'user_id': current_user_id}).sort('created_at', -1))
        
        # Convert ObjectId to string and calculate streaks
        for habit in habits:
            habit['_id'] = str(habit['_id'])
            habit['created_at'] = habit['created_at'].isoformat()
            habit['updated_at'] = habit['updated_at'].isoformat()
            
            # Calculate current streak
            habit['current_streak'] = calculate_current_streak(habit['entries'])
            habit['best_streak'] = calculate_best_streak(habit['entries'])
            
            # Calculate completion rate for the current week/month
            today = datetime.utcnow().date()
            if habit['frequency'] == 'daily':
                start_date = today - timedelta(days=7)
                expected_days = 7
            else:  # weekly
                start_date = today - timedelta(days=30)
                expected_days = 4  # 4 weeks
            
            recent_entries = [
                entry for entry in habit['entries'] 
                if datetime.fromisoformat(entry['date']).date() >= start_date
            ]
            habit['recent_completion_rate'] = (len(recent_entries) / expected_days) * 100 if expected_days > 0 else 0
        
        return jsonify({'habits': habits}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@habits_bp.route('/', methods=['POST'])
@token_required
def create_habit(current_user_id):
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({'error': 'Habit name is required'}), 400
        
        habit_data = {
            'user_id': current_user_id,
            'name': data['name'],
            'description': data.get('description', ''),
            'frequency': data.get('frequency', 'daily'),  # daily, weekly
            'target_value': data.get('target_value', 1),  # for quantifiable habits
            'unit': data.get('unit', ''),  # e.g., 'minutes', 'pages', 'glasses'
            'category': data.get('category', 'general'),
            'color': data.get('color', '#3B82F6'),
            'entries': [],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = current_app.mongo.db.habits.insert_one(habit_data)
        habit_data['_id'] = str(result.inserted_id)
        habit_data['created_at'] = habit_data['created_at'].isoformat()
        habit_data['updated_at'] = habit_data['updated_at'].isoformat()
        habit_data['current_streak'] = 0
        habit_data['best_streak'] = 0
        habit_data['recent_completion_rate'] = 0
        
        return jsonify({
            'message': 'Habit created successfully',
            'habit': habit_data
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@habits_bp.route('/<habit_id>/entry', methods=['POST'])
@token_required
def add_habit_entry(current_user_id, habit_id):
    try:
        data = request.get_json()
        
        entry_date = data.get('date', datetime.utcnow().isoformat())
        value = data.get('value', 1)
        notes = data.get('notes', '')
        
        # Check if entry for this date already exists
        habit = current_app.mongo.db.habits.find_one({
            '_id': ObjectId(habit_id),
            'user_id': current_user_id
        })
        
        if not habit:
            return jsonify({'error': 'Habit not found'}), 404
        
        # Remove existing entry for the same date if it exists
        existing_entries = [
            entry for entry in habit['entries']
            if entry['date'][:10] != entry_date[:10]  # Compare date part only
        ]
        
        # Add new entry
        new_entry = {
            'date': entry_date,
            'value': value,
            'notes': notes,
            'created_at': datetime.utcnow().isoformat()
        }
        existing_entries.append(new_entry)
        
        # Update habit
        current_app.mongo.db.habits.update_one(
            {'_id': ObjectId(habit_id), 'user_id': current_user_id},
            {
                '$set': {
                    'entries': existing_entries,
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        return jsonify({
            'message': 'Habit entry added successfully',
            'entry': new_entry
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@habits_bp.route('/<habit_id>', methods=['PUT'])
@token_required
def update_habit(current_user_id, habit_id):
    try:
        data = request.get_json()
        
        update_data = {'updated_at': datetime.utcnow()}
        
        allowed_fields = ['name', 'description', 'frequency', 'target_value', 'unit', 'category', 'color']
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        result = current_app.mongo.db.habits.update_one(
            {'_id': ObjectId(habit_id), 'user_id': current_user_id},
            {'$set': update_data}
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Habit not found'}), 404
        
        return jsonify({'message': 'Habit updated successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@habits_bp.route('/<habit_id>', methods=['DELETE'])
@token_required
def delete_habit(current_user_id, habit_id):
    try:
        result = current_app.mongo.db.habits.delete_one(
            {'_id': ObjectId(habit_id), 'user_id': current_user_id}
        )
        
        if result.deleted_count == 0:
            return jsonify({'error': 'Habit not found'}), 404
        
        return jsonify({'message': 'Habit deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@habits_bp.route('/stats', methods=['GET'])
@token_required
def get_habit_stats(current_user_id):
    try:
        habits = list(current_app.mongo.db.habits.find({'user_id': current_user_id}))
        
        total_habits = len(habits)
        active_habits = 0
        total_entries_today = 0
        
        today = datetime.utcnow().date().isoformat()
        
        for habit in habits:
            # Check if habit has entry for today
            today_entries = [
                entry for entry in habit['entries']
                if entry['date'][:10] == today
            ]
            if today_entries:
                total_entries_today += 1
            
            # Check if habit is active (has entries in last 7 days)
            recent_entries = [
                entry for entry in habit['entries']
                if datetime.fromisoformat(entry['date']).date() >= datetime.utcnow().date() - timedelta(days=7)
            ]
            if recent_entries:
                active_habits += 1
        
        completion_rate = (total_entries_today / total_habits * 100) if total_habits > 0 else 0
        
        return jsonify({
            'stats': {
                'total_habits': total_habits,
                'active_habits': active_habits,
                'today_completion_rate': completion_rate,
                'entries_today': total_entries_today
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def calculate_current_streak(entries):
    if not entries:
        return 0
    
    # Sort entries by date (newest first)
    sorted_entries = sorted(entries, key=lambda x: x['date'], reverse=True)
    
    current_date = datetime.utcnow().date()
    streak = 0
    
    for entry in sorted_entries:
        entry_date = datetime.fromisoformat(entry['date']).date()
        
        if entry_date == current_date:
            streak += 1
            current_date -= timedelta(days=1)
        elif entry_date == current_date - timedelta(days=1):
            streak += 1
            current_date = entry_date - timedelta(days=1)
        else:
            break
    
    return streak

def calculate_best_streak(entries):
    if not entries:
        return 0
    
    # Sort entries by date
    sorted_entries = sorted(entries, key=lambda x: x['date'])
    
    max_streak = 0
    current_streak = 0
    previous_date = None
    
    for entry in sorted_entries:
        entry_date = datetime.fromisoformat(entry['date']).date()
        
        if previous_date is None or entry_date == previous_date + timedelta(days=1):
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 1
        
        previous_date = entry_date
    
    return max_streak
