release: cd server && python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py import_models
web: cd server && gunicorn server.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${GUNICORN_WORKERS:-3} --timeout ${GUNICORN_TIMEOUT:-60}
