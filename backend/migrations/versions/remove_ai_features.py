"""Remove the Ollama features: predictions, anomaly alerts, model settings and what pointed at them.

The data the model produced is deleted. Records people entered themselves stay, including
workshop tasks that were created from a prediction: they keep their title and lose the link.
"""
import os

from alembic import op
import sqlalchemy as sa

revision = 'remove_ai_features'
down_revision = 'feature_passkeys'
branch_labels = None
depends_on = None

AI_NOTIFICATION_TYPES = ('ai_prediction', 'mileage_prediction', 'fuel_anomaly')
AI_ACTIVITY_EVENTS = ('ai_settings_updated', 'ai_cache_flushed')
AI_SCHEDULED_JOBS = ('check_predictions', 'ollama_probe')
AI_SETTING_KEYS = ('chat_classifier_enabled', 'chat_output_classifier_enabled')
AI_SETTING_PREFIX = 'ollama_model_'
AI_CACHE_PATTERNS = ('ai_cache:*', 'ollama:*')
REDIS_TIMEOUT_SECONDS = 2
DROPPED_COLUMNS = (
    ('notification_logs', 'prediction_id'),
    ('appointment_tasks', 'prediction_id'),
    ('vehicles', 'prediction_accuracy_score'),
    ('vehicles', 'last_prediction_at'),
    ('fuel_entries', 'ocr_populated'),
    ('users', 'email_smart_alerts'),
)


def _names(values):
    return sa.bindparam('names', value=list(values), expanding=True)


def _delete_generated_rows(connection):
    connection.execute(sa.text(
        'DELETE FROM notification_logs WHERE prediction_id IS NOT NULL OR notification_type IN :names'
    ).bindparams(_names(AI_NOTIFICATION_TYPES)))
    # The signature vouched for the prediction a task was linked to; without it the task stands alone.
    connection.execute(sa.text('UPDATE appointment_tasks SET source_signature = NULL WHERE prediction_id IS NOT NULL'))
    connection.execute(sa.text("DELETE FROM due_dismissals WHERE kind = 'prediction'"))
    connection.execute(sa.text("DELETE FROM import_identities WHERE entity_kind = 'predictions'"))
    connection.execute(sa.text('DELETE FROM scheduled_effects WHERE job_name IN :names').bindparams(_names(AI_SCHEDULED_JOBS)))
    connection.execute(sa.text('DELETE FROM scheduled_job_runs WHERE job_name IN :names').bindparams(_names(AI_SCHEDULED_JOBS)))
    connection.execute(sa.text('DELETE FROM activity_logs WHERE event_type IN :names').bindparams(_names(AI_ACTIVITY_EVENTS)))
    connection.execute(sa.text(
        'DELETE FROM app_settings WHERE key IN :names OR substr(key, 1, :length) = :prefix'
    ).bindparams(_names(AI_SETTING_KEYS), length=len(AI_SETTING_PREFIX), prefix=AI_SETTING_PREFIX))


def _forget_cached_answers():
    """Best effort: the cache empties itself within a week when it cannot be reached now."""
    address = os.environ.get('REDIS_URL')
    if not address:
        return
    try:
        import redis
        client = redis.Redis.from_url(address, socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
                                      socket_timeout=REDIS_TIMEOUT_SECONDS)
        for pattern in AI_CACHE_PATTERNS:
            for key in client.scan_iter(match=pattern):
                client.delete(key)
    except Exception:
        return


def upgrade():
    _delete_generated_rows(op.get_bind())
    for table, column in DROPPED_COLUMNS:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column(column)
    op.drop_table('prediction_alerts')
    _forget_cached_answers()


def downgrade():
    """Restore the empty structures the previous release expects. The deleted data does not come back."""
    op.create_table('prediction_alerts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('alert_type', sa.String(50), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('predicted_mileage', sa.Integer()),
        sa.Column('predicted_date', sa.Date()),
        sa.Column('confidence_score', sa.Float()),
        sa.Column('severity', sa.String(20)),
        sa.Column('dismissed', sa.Boolean()),
        sa.Column('dismissed_at', sa.DateTime()),
        sa.Column('actioned', sa.Boolean()),
        sa.Column('actioned_at', sa.DateTime()),
        sa.Column('i18n_key', sa.String(100)),
        sa.Column('i18n_params', sa.JSON()),
        sa.Column('description_en_us', sa.Text()),
        sa.Column('description_ro', sa.Text()),
        sa.Column('description_es', sa.Text()),
        sa.Column('generated_by', sa.String(30)),
        sa.Column('model_version', sa.String(20)),
        sa.Column('title', sa.String(255)),
        sa.Column('urgency', sa.String(20)),
        sa.Column('estimated_cost', sa.Numeric(10, 2)),
        sa.Column('recommended_action', sa.Text()),
        sa.Column('source_data', sa.JSON()),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', name='fk_prediction_alerts_user_id')),
        sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('vehicles.id'), nullable=False),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('expires_at', sa.DateTime()))
    op.create_index('ix_prediction_alerts_vehicle_id', 'prediction_alerts', ['vehicle_id'])
    op.create_index('ix_prediction_alerts_user_id', 'prediction_alerts', ['user_id'])
    with op.batch_alter_table('notification_logs') as batch_op:
        batch_op.add_column(sa.Column('prediction_id', sa.Integer()))
        batch_op.create_foreign_key('notification_logs_prediction_id_fkey', 'prediction_alerts', ['prediction_id'], ['id'])
    with op.batch_alter_table('appointment_tasks') as batch_op:
        batch_op.add_column(sa.Column('prediction_id', sa.Integer()))
        batch_op.create_foreign_key('appointment_tasks_prediction_id_fkey', 'prediction_alerts', ['prediction_id'], ['id'],
                                    ondelete='SET NULL')
    with op.batch_alter_table('vehicles') as batch_op:
        batch_op.add_column(sa.Column('prediction_accuracy_score', sa.Float()))
        batch_op.add_column(sa.Column('last_prediction_at', sa.DateTime()))
    with op.batch_alter_table('fuel_entries') as batch_op:
        batch_op.add_column(sa.Column('ocr_populated', sa.Boolean()))
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('email_smart_alerts', sa.Boolean()))
