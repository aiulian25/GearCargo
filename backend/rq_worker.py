"""
RQ worker entrypoint for GearCargo background tasks (opt-in).

Only needed when running with TASK_QUEUE_BACKEND=rq. The default deployment
uses the in-process thread backend and does NOT require this process.

Run alongside the web container, sharing the same image, env and Redis:

    python rq_worker.py

Example optional compose service (add to your deployment when you enable RQ):

    rq-worker:
      image: <same image as backend>
      command: python rq_worker.py
      environment:
        TASK_QUEUE_BACKEND: "rq"
        REDIS_URL: "redis://redis:6379/0"
        # plus the same SECRET_KEY / ENCRYPTION_KEY / DATABASE_URL / VOLUMES_PATH
        # as the web service, so tasks (e.g. OCR) can read files and the DB.
      depends_on: [redis, db]
      restart: unless-stopped

The worker builds one Flask app and pushes its application context once, so
every job runs with db / current_app available (SimpleWorker, no forking).
"""

from app import create_app
from app.services.task_queue import build_worker


def main():
    app = create_app()
    with app.app_context():
        worker = build_worker(app)
        app.logger.info('RQ worker starting (queue=%s)', app.config.get('TASK_QUEUE_NAME', 'gearcargo'))
        worker.work(with_scheduler=False)


if __name__ == '__main__':
    main()
