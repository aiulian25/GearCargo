"""Notices for backup copies that keep failing, in the language of each account.

A failed copy changes nothing a person would see, so without a notice it stays unknown until
the day the copy is needed.
"""
import functools

from flask import current_app

from app import db
from app.models import BackupSchedule, User

DEFAULT_LANGUAGE = 'en'
EXTERNAL_COPY_FAILED = 'external-copy-failed'
MIRROR_FAILING = 'mirror-failing'
NOTICE_TAG_PREFIX = 'backup-'
NOTICE_DATA = {'type': 'backup', 'status': 'failure', 'url': '/settings'}

# (title, body) by notice and language.
NOTICE_TEXT = {
    EXTERNAL_COPY_FAILED: {
        'en': ('External backup failed',
               'Your backup is saved on the server, but it could not be uploaded to your external destination.'),
        'ro': ('Backupul extern a eșuat',
               'Backupul este salvat pe server, dar nu a putut fi încărcat la destinația externă.'),
        'es': ('La copia externa ha fallado',
               'La copia de seguridad está guardada en el servidor, pero no se pudo subir al destino externo.'),
    },
    MIRROR_FAILING: {
        'en': ('Second backup copy is failing',
               'Copying backups to the second storage keeps failing. New backups stay on this server only. '
               'Check that the storage is connected and writable.'),
        'ro': ('A doua copie de backup eșuează',
               'Copierea backup-urilor în al doilea spațiu de stocare eșuează în continuare. Backup-urile noi '
               'rămân doar pe acest server. Verifică dacă spațiul de stocare este conectat și permite scrierea.'),
        'es': ('La segunda copia de seguridad está fallando',
               'La copia al segundo almacenamiento sigue fallando. Las copias nuevas se quedan solo en este '
               'servidor. Comprueba que el almacenamiento esté conectado y permita escribir.'),
    },
}


def _best_effort(notify):
    """A notice that cannot be sent must never fail the job that found the problem."""
    @functools.wraps(notify)
    def guarded(*arguments):
        try:
            notify(*arguments)
            # In a scheduled job the notice is a queued delivery, and each job owns its session:
            # uncommitted, it is rolled back when the job that asked for it ends.
            db.session.commit()
        except Exception as failure:
            db.session.rollback()
            current_app.logger.warning('Backup notice could not be sent (%s)', type(failure).__name__)
    return guarded


def _send(user, notice):
    if not user.notifications_enabled:
        return
    from app.routes.push import send_push_to_user
    texts = NOTICE_TEXT[notice]
    title, body = texts.get(user.language, texts[DEFAULT_LANGUAGE])
    send_push_to_user(user.id, title, body, data=dict(NOTICE_DATA), tag=NOTICE_TAG_PREFIX + notice)


@_best_effort
def notify_external_copy_failed(user_id):
    """The account's scheduled backup never reached its external destination."""
    user = db.session.get(User, user_id)
    schedule = BackupSchedule.query.filter_by(user_id=user_id).first()
    if user and user.is_active and schedule and schedule.notify_on_failure:
        _send(user, EXTERNAL_COPY_FAILED)


@_best_effort
def notify_mirror_failing():
    """Every administrator hears that the second copy has stopped working."""
    for administrator in User.query.filter_by(is_admin=True, is_active=True).all():
        _send(administrator, MIRROR_FAILING)
