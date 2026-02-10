"""
GearCargo - Todo Routes
"""

from datetime import datetime
from flask import Blueprint, request, jsonify

from app import db
from app.models import Vehicle
from app.models.todo import Todo
from app.routes.auth import token_required

todos_bp = Blueprint('todos', __name__)


@todos_bp.route('', methods=['GET'])
@token_required
def get_todos(current_user):
    """Get todos."""
    vehicle_id = request.args.get('vehicle_id', type=int)
    status = request.args.get('status')  # pending, completed, all
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = Todo.query.filter_by(user_id=current_user.id)
    
    if vehicle_id:
        query = query.filter(Todo.vehicle_id == vehicle_id)
    
    if status:
        if status == 'pending':
            query = query.filter(Todo.completed == False)
        elif status == 'completed':
            query = query.filter(Todo.completed == True)
    
    todos = query.order_by(Todo.due_date.asc().nullslast(), Todo.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'todos': [t.to_dict() for t in todos.items],
        'total': todos.total,
        'pages': todos.pages,
        'current_page': page,
    })


@todos_bp.route('', methods=['POST'])
@token_required
def create_todo(current_user):
    """Create a new todo."""
    data = request.get_json()
    
    # Validate vehicle if provided
    vehicle_id = data.get('vehicle_id')
    if vehicle_id:
        vehicle = Vehicle.query.filter_by(
            id=vehicle_id,
            user_id=current_user.id
        ).first()
        if not vehicle:
            return jsonify({'error': 'Vehicle not found'}), 404
    
    if not data.get('title'):
        return jsonify({'error': 'Title is required'}), 400
    
    # Parse due date
    due_date = None
    if data.get('due_date'):
        try:
            due_date = datetime.fromisoformat(data['due_date'].replace('Z', '+00:00')).date()
        except (ValueError, AttributeError):
            pass
    
    todo = Todo(
        user_id=current_user.id,
        vehicle_id=vehicle_id,
        title=data['title'],
        description=data.get('description'),
        due_date=due_date,
        priority=data.get('priority', 'medium'),
        completed=False,
    )
    
    db.session.add(todo)
    db.session.commit()
    
    return jsonify({
        'message': 'Todo created',
        'todo': todo.to_dict()
    }), 201


@todos_bp.route('/<int:todo_id>', methods=['GET'])
@token_required
def get_todo(current_user, todo_id):
    """Get a specific todo."""
    todo = Todo.query.filter_by(
        id=todo_id,
        user_id=current_user.id
    ).first()
    
    if not todo:
        return jsonify({'error': 'Todo not found'}), 404
    
    return jsonify(todo.to_dict())


@todos_bp.route('/<int:todo_id>', methods=['PUT'])
@token_required
def update_todo(current_user, todo_id):
    """Update a todo."""
    todo = Todo.query.filter_by(
        id=todo_id,
        user_id=current_user.id
    ).first()
    
    if not todo:
        return jsonify({'error': 'Todo not found'}), 404
    
    data = request.get_json()
    
    if 'title' in data:
        todo.title = data['title']
    if 'description' in data:
        todo.description = data['description']
    if 'due_date' in data:
        if data['due_date']:
            try:
                todo.due_date = datetime.fromisoformat(data['due_date'].replace('Z', '+00:00')).date()
            except (ValueError, AttributeError):
                pass
        else:
            todo.due_date = None
    if 'priority' in data:
        todo.priority = data['priority']
    if 'completed' in data:
        if data['completed']:
            todo.mark_complete()
        else:
            todo.mark_incomplete()
    
    db.session.commit()
    
    return jsonify({
        'message': 'Todo updated',
        'todo': todo.to_dict()
    })


@todos_bp.route('/<int:todo_id>', methods=['DELETE'])
@token_required
def delete_todo(current_user, todo_id):
    """Delete a todo."""
    todo = Todo.query.filter_by(
        id=todo_id,
        user_id=current_user.id
    ).first()
    
    if not todo:
        return jsonify({'error': 'Todo not found'}), 404
    
    db.session.delete(todo)
    db.session.commit()
    
    return jsonify({'message': 'Todo deleted'})


@todos_bp.route('/<int:todo_id>/complete', methods=['POST'])
@token_required
def complete_todo(current_user, todo_id):
    """Mark a todo as complete."""
    todo = Todo.query.filter_by(
        id=todo_id,
        user_id=current_user.id
    ).first()
    
    if not todo:
        return jsonify({'error': 'Todo not found'}), 404
    
    todo.mark_complete()
    db.session.commit()
    
    return jsonify({
        'message': 'Todo completed',
        'todo': todo.to_dict()
    })


@todos_bp.route('/<int:todo_id>/incomplete', methods=['POST'])
@token_required
def incomplete_todo(current_user, todo_id):
    """Mark a todo as incomplete."""
    todo = Todo.query.filter_by(
        id=todo_id,
        user_id=current_user.id
    ).first()
    
    if not todo:
        return jsonify({'error': 'Todo not found'}), 404
    
    todo.mark_incomplete()
    db.session.commit()
    
    return jsonify({
        'message': 'Todo marked incomplete',
        'todo': todo.to_dict()
    })
