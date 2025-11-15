web: uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
worker: celery -A app.core.celery_app worker --loglevel=info --pool=threads --concurrency=4
