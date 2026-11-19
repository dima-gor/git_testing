# Convenience targets. Run "make help" for the list.
#
#   make install
#   make quiz ARGS="--course 123 --publish"
#   make jupyter ARGS="--dry-run"
#   make docker-run ARGS="--example quiz --course 123"

.PHONY: help install test jupyter quiz capture docker-build docker-run clean

VENV   := .venv
PY     := $(VENV)/bin/python
IMAGE  := cg-authoring
ARGS   ?=

help:  ## Show this help
	@grep -E "^[a-zA-Z_-]+:.*?## " $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

$(PY):
	python3.12 -m venv $(VENV) || python3 -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements.txt -r requirements-dev.txt

install: $(PY)  ## Create .venv and install dependencies (Python 3.12+)

test: $(PY)  ## Run the unit tests (offline)
	$(PY) -m pytest -q

jupyter: $(PY)  ## Push the Jupyter example: make jupyter ARGS="--course 123"
	$(PY) -m scripts.push_assignment --example jupyter $(ARGS)

quiz: $(PY)  ## Push the quiz example: make quiz ARGS="--course 123"
	$(PY) -m scripts.push_assignment --example quiz $(ARGS)

capture: $(PY)  ## Print an assignment config: make capture ARGS="--assignment 123"
	$(PY) -m scripts.capture_config $(ARGS)

docker-build:  ## Build the Docker image
	docker build -t $(IMAGE) .

docker-run: docker-build  ## Run inside Docker: make docker-run ARGS="--example quiz --course 123"
	docker run --rm -it -e CG_HOST -e CG_TENANT -e CG_USERNAME -e CG_PASSWORD -v "$(PWD)":/repo $(IMAGE) $(ARGS)

clean:  ## Remove .venv and build output
	rm -rf $(VENV) build __pycache__ scripts/__pycache__ tests/__pycache__
