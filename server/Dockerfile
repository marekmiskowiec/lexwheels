FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace/server

COPY server/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /workspace
RUN chmod +x /workspace/server/entrypoint.sh

EXPOSE 8000

CMD ["/workspace/server/entrypoint.sh"]
