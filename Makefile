.PHONY: install run test lint docker

install:  ## create a virtualenv and install everything
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt

run:  ## start the API with auto-reload (needs a .env file)
	uvicorn app.main:create_app --factory --reload --env-file .env

test:  ## run the Python and JavaScript test suites
	pytest
	node --test tests/js/*.test.js

lint:  ## style and bug checks
	ruff check .

docker:  ## build and start with Docker
	docker compose up --build
