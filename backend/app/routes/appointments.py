"""Owner-scoped manual workshop appointments; never contacts or books a shop."""
from flask import Blueprint, jsonify, request
from app import db
from app.models import Vehicle, Entry
from app.models.appointment import Appointment, AppointmentExpense
from app.routes.auth import token_required
from app.services.mutations import mutation_endpoint, commit_mutation
from app.services import appointments as workflow
from app.utils.timeutils import utc_naive_now

appointments_bp = Blueprint('appointments', __name__)


def vehicle(user, ident, write=False):
    record = Vehicle.query.filter_by(id=ident, user_id=user.id).first_or_404()
    if write and record.archived: workflow.invalid('vehicle_id', 'archived')
    return record


def owned(user, appointment_id, write=True):
    record = Appointment.query.filter_by(id=appointment_id, user_id=user.id).first_or_404()
    vehicle(user, record.vehicle_id, write)
    return record


def saved(record, status=200):
    record.updated_at = utc_naive_now()
    workflow.sync_preparation(record)
    commit_mutation()
    return jsonify(record.to_dict()), status


@appointments_bp.route('', methods=['GET'])
@token_required
def list_appointments(user):
    car = vehicle(user, request.args.get('vehicle_id', type=int))
    return jsonify({'appointments': [r.to_dict() for r in Appointment.query.filter_by(user_id=user.id, vehicle_id=car.id).order_by(Appointment.start_at.desc())]})


@appointments_bp.route('/work', methods=['GET'])
@token_required
def available_work(user):
    from app.services.due import build_due_items
    car = vehicle(user, request.args.get('vehicle_id', type=int))
    work = []
    fields = {'reminder': 'reminder_id', 'todo': 'todo_id', 'service': 'service_id', 'prediction': 'prediction_id'}
    for item in build_due_items(user.id):
        if item['vehicle_id'] != car.id or item['kind'] not in fields: continue
        field = fields[item['kind']]
        target = workflow.TARGETS[field].query.filter_by(id=item['ref_id'], user_id=user.id).first()
        if target and not (field == 'reminder_id' and target.reminder_type == 'workshop_preparation'):
            work.append({'title': item['title'], field: target.id})
    return jsonify({'work': work})


@appointments_bp.route('/<int:appointment_id>', methods=['GET'])
@token_required
def get_appointment(user, appointment_id):
    return jsonify(owned(user, appointment_id, False).to_dict())


@appointments_bp.route('', methods=['POST'])
@token_required
@mutation_endpoint(Appointment)
def create_appointment(user):
    data = request.get_json() or {}
    car = vehicle(user, data.get('vehicle_id'), True)
    if data.get('status', 'requested') != 'requested': workflow.invalid('status')
    record = Appointment(user_id=user.id, vehicle_id=car.id, status='requested', prepare_minutes=1440, notify_push=False, notify_email=False)
    workflow.apply_details(record, data)
    db.session.add(record)
    workflow.set_tasks(record, data.get('tasks', []))
    return saved(record, 201)


@appointments_bp.route('/<int:appointment_id>', methods=['PUT'])
@token_required
@mutation_endpoint(Appointment, 'appointment_id')
def edit_appointment(user, appointment_id):
    record = owned(user, appointment_id)
    if record.status in ('completed', 'cancelled'): workflow.invalid('status')
    data = request.get_json() or {}
    if 'status' in data and data['status'] != record.status: workflow.invalid('status')
    previous = (record.start_at, record.end_at, record.time_zone, record.shop_name, record.shop_contact)
    workflow.apply_details(record, data)
    if previous != (record.start_at, record.end_at, record.time_zone, record.shop_name, record.shop_contact):
        if record.dropoff_at: workflow.invalid('start_local')
        record.status = 'requested'; record.confirmed_at = None
    if 'tasks' in data: workflow.set_tasks(record, data['tasks'])
    return saved(record)


@appointments_bp.route('/<int:appointment_id>/confirm', methods=['POST'])
@token_required
@mutation_endpoint(Appointment, 'appointment_id')
def confirm_appointment(user, appointment_id):
    record = owned(user, appointment_id)
    if record.status != 'requested': workflow.invalid('status')
    if (request.get_json() or {}).get('arranged_externally') is not True: workflow.invalid('arranged_externally')
    record.status = 'confirmed'; record.confirmed_at = utc_naive_now()
    return saved(record)


@appointments_bp.route('/<int:appointment_id>/cancel', methods=['POST'])
@token_required
@mutation_endpoint(Appointment, 'appointment_id')
def cancel_appointment(user, appointment_id):
    record = owned(user, appointment_id)
    if record.status == 'completed': workflow.invalid('status')
    record.status = 'cancelled'
    return saved(record)


@appointments_bp.route('/<int:appointment_id>/dropoff', methods=['POST'])
@token_required
@mutation_endpoint(Appointment, 'appointment_id')
def dropoff(user, appointment_id):
    record = owned(user, appointment_id)
    if record.status != 'confirmed': workflow.invalid('status')
    if not record.dropoff_at: record.dropoff_at = utc_naive_now()
    return saved(record)


@appointments_bp.route('/<int:appointment_id>/complete', methods=['POST'])
@token_required
@mutation_endpoint(Appointment, 'appointment_id')
def complete(user, appointment_id):
    record = owned(user, appointment_id)
    if record.status != 'confirmed' or not record.dropoff_at: workflow.invalid('status')
    data = request.get_json() or {}
    entries = data.get('entry_ids', []); tasks = data.get('resolved_task_ids', [])
    for values in (entries, tasks):
        if not isinstance(values, list) or len(values) > 100 or any(type(v) is not int for v in values) or len(set(values)) != len(values): workflow.invalid('completion')
    if not entries and data.get('no_cost') is not True: workflow.invalid('entry_ids')
    for ident in sorted(entries):
        entry = Entry.query.filter_by(id=ident, user_id=user.id, vehicle_id=record.vehicle_id).with_for_update().first()
        if not entry or entry.type not in ('service', 'repair') or AppointmentExpense.query.filter_by(entry_id=ident).first(): workflow.invalid('entry_ids')
        record.expenses.append(AppointmentExpense(user_id=user.id, vehicle_id=record.vehicle_id, entry_id=ident))
    mapping = {task.id: task for task in record.tasks}
    for ident in tasks:
        if ident not in mapping: workflow.invalid('tasks')
        try:
            workflow.resolve_task(mapping[ident])
        except workflow.InvalidFieldError:
            raise
        except (ValueError, OverflowError):
            workflow.invalid('tasks')
    record.status = 'completed'; record.pickup_at = utc_naive_now()
    return saved(record)
