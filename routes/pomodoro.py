from flask import Blueprint, request, jsonify, current_app
from routes.auth import token_required
from datetime import datetime, timedelta
from bson import ObjectId

pomodoro_bp = Blueprint('pomodoro', __name__)

@pomodoro_bp.route('/sessions', methods=['GET'])
@token_required
def get_sessions(current_user_id):
    try:
        # Get query parameters for filtering
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        # Build query
        query = {'user_id': current_user_id}
        
        if date_from or date_to:
            date_query = {}
            if date_from:
                date_query['$gte'] = datetime.fromisoformat(date_from)
            if date_to:
                date_query['$lte'] = datetime.fromisoformat(date_to)
            query['created_at'] = date_query
        
        sessions = list(current_app.mongo.db.pomodoro_sessions.find(query).sort('created_at', -1))
        
        # Convert ObjectId to string
        for session in sessions:
            session['_id'] = str(session['_id'])
            session['created_at'] = session['created_at'].isoformat()
            session['updated_at'] = session['updated_at'].isoformat()
            if session.get('completed_at'):
                session['completed_at'] = session['completed_at'].isoformat()
        
        return jsonify({'sessions': sessions}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pomodoro_bp.route('/sessions', methods=['POST'])
@token_required
def start_session(current_user_id):
    try:
        data = request.get_json()
        
        session_data = {
            'user_id': current_user_id,
            'type': data.get('type', 'work'),  # work, short_break, long_break
            'duration': data.get('duration', 25),  # duration in minutes
            'task_title': data.get('task_title', ''),
            'status': 'active',  # active, completed, cancelled
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'completed_at': None
        }
        
        result = current_app.mongo.db.pomodoro_sessions.insert_one(session_data)
        session_data['_id'] = str(result.inserted_id)
        session_data['created_at'] = session_data['created_at'].isoformat()
        session_data['updated_at'] = session_data['updated_at'].isoformat()
        
        return jsonify({
            'message': 'Pomodoro session started',
            'session': session_data
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pomodoro_bp.route('/sessions/<session_id>/complete', methods=['PUT'])
@token_required
def complete_session(current_user_id, session_id):
    try:
        data = request.get_json()
        
        update_data = {
            'status': 'completed',
            'completed_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Optional: add notes about the session
        if data.get('notes'):
            update_data['notes'] = data['notes']
        
        result = current_app.mongo.db.pomodoro_sessions.update_one(
            {'_id': ObjectId(session_id), 'user_id': current_user_id},
            {'$set': update_data}
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Session not found'}), 404
        
        return jsonify({'message': 'Session completed successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pomodoro_bp.route('/sessions/<session_id>/cancel', methods=['PUT'])
@token_required
def cancel_session(current_user_id, session_id):
    try:
        update_data = {
            'status': 'cancelled',
            'updated_at': datetime.utcnow()
        }
        
        result = current_app.mongo.db.pomodoro_sessions.update_one(
            {'_id': ObjectId(session_id), 'user_id': current_user_id},
            {'$set': update_data}
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Session not found'}), 404
        
        return jsonify({'message': 'Session cancelled successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pomodoro_bp.route('/stats', methods=['GET'])
@token_required
def get_pomodoro_stats(current_user_id):
    try:
        # Get stats for different time periods
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        
        # Today's stats
        today_pipeline = [
            {
                '$match': {
                    'user_id': current_user_id,
                    'created_at': {'$gte': today},
                    'status': 'completed'
                }
            },
            {
                '$group': {
                    '_id': '$type',
                    'count': {'$sum': 1},
                    'total_duration': {'$sum': '$duration'}
                }
            }
        ]
        
        today_stats = list(current_app.mongo.db.pomodoro_sessions.aggregate(today_pipeline))
        
        # Week's stats
        week_pipeline = [
            {
                '$match': {
                    'user_id': current_user_id,
                    'created_at': {'$gte': week_start},
                    'status': 'completed'
                }
            },
            {
                '$group': {
                    '_id': '$type',
                    'count': {'$sum': 1},
                    'total_duration': {'$sum': '$duration'}
                }
            }
        ]
        
        week_stats = list(current_app.mongo.db.pomodoro_sessions.aggregate(week_pipeline))
        
        # Month's stats
        month_pipeline = [
            {
                '$match': {
                    'user_id': current_user_id,
                    'created_at': {'$gte': month_start},
                    'status': 'completed'
                }
            },
            {
                '$group': {
                    '_id': '$type',
                    'count': {'$sum': 1},
                    'total_duration': {'$sum': '$duration'}
                }
            }
        ]
        
        month_stats = list(current_app.mongo.db.pomodoro_sessions.aggregate(month_pipeline))
        
        # Format stats
        def format_stats(stats_list):
            result = {'work': 0, 'short_break': 0, 'long_break': 0, 'total_duration': 0}
            for stat in stats_list:
                session_type = stat['_id']
                if session_type in result:
                    result[session_type] = stat['count']
                result['total_duration'] += stat['total_duration']
            return result
        
        # Get productivity streak (consecutive days with at least one completed work session)
        streak_pipeline = [
            {
                '$match': {
                    'user_id': current_user_id,
                    'type': 'work',
                    'status': 'completed'
                }
            },
            {
                '$group': {
                    '_id': {
                        'year': {'$year': '$created_at'},
                        'month': {'$month': '$created_at'},
                        'day': {'$dayOfMonth': '$created_at'}
                    },
                    'count': {'$sum': 1}
                }
            },
            {
                '$sort': {'_id': -1}
            }
        ]
        
        daily_work_sessions = list(current_app.mongo.db.pomodoro_sessions.aggregate(streak_pipeline))
        
        # Calculate current streak
        current_streak = 0
        if daily_work_sessions:
            current_date = datetime.utcnow().date()
            for session_day in daily_work_sessions:
                session_date = datetime(
                    session_day['_id']['year'],
                    session_day['_id']['month'],
                    session_day['_id']['day']
                ).date()
                
                if session_date == current_date or (current_streak > 0 and session_date == current_date - timedelta(days=current_streak)):
                    current_streak += 1
                    current_date = session_date - timedelta(days=1)
                else:
                    break
        
        return jsonify({
            'stats': {
                'today': format_stats(today_stats),
                'this_week': format_stats(week_stats),
                'this_month': format_stats(month_stats),
                'current_streak': current_streak
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pomodoro_bp.route('/settings', methods=['GET'])
@token_required
def get_settings(current_user_id):
    try:
        settings = current_app.mongo.db.pomodoro_settings.find_one({'user_id': current_user_id})
        
        if not settings:
            # Return default settings
            default_settings = {
                'work_duration': 25,
                'short_break_duration': 5,
                'long_break_duration': 15,
                'long_break_interval': 4,  # After how many work sessions
                'auto_start_breaks': False,
                'auto_start_work': False,
                'notification_sound': True,
                'notification_desktop': True
            }
            return jsonify({'settings': default_settings}), 200
        
        settings['_id'] = str(settings['_id'])
        return jsonify({'settings': settings}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@pomodoro_bp.route('/settings', methods=['PUT'])
@token_required
def update_settings(current_user_id):
    try:
        data = request.get_json()
        
        settings_data = {
            'user_id': current_user_id,
            'work_duration': data.get('work_duration', 25),
            'short_break_duration': data.get('short_break_duration', 5),
            'long_break_duration': data.get('long_break_duration', 15),
            'long_break_interval': data.get('long_break_interval', 4),
            'auto_start_breaks': data.get('auto_start_breaks', False),
            'auto_start_work': data.get('auto_start_work', False),
            'notification_sound': data.get('notification_sound', True),
            'notification_desktop': data.get('notification_desktop', True),
            'updated_at': datetime.utcnow()
        }
        
        result = current_app.mongo.db.pomodoro_settings.update_one(
            {'user_id': current_user_id},
            {'$set': settings_data},
            upsert=True
        )
        
        return jsonify({'message': 'Settings updated successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
