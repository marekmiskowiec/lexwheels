#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ "${LEXWHEELS_IMPORT_MODELS_ON_BOOT:-1}" = "1" ]; then
  python manage.py import_models
fi

exec gunicorn server.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers ${GUNICORN_WORKERS:-3} \
  --timeout ${GUNICORN_TIMEOUT:-60}
