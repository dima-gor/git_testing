# Run push_assignment inside a small Python image (nothing installed on your machine).
#
#   docker build -t cg-authoring .
#   docker run --rm -it -v "$PWD":/repo cg-authoring --example quiz --course 123
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

RUN useradd --create-home --shell /bin/bash cg
USER cg
WORKDIR /repo

ENTRYPOINT ["python", "-m", "scripts.push_assignment"]
