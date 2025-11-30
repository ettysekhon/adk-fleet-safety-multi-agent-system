# Makefile using Agent Starter Pack (https://github.com/GoogleCloudPlatform/agent-starter-pack)

PROJECT_ID ?= $(shell gcloud config get-value project)
REGION ?= europe-west2
STAGING_BUCKET ?= gs://$(PROJECT_ID)-agent-staging

PYTHON_VERSION ?= 3.12

install:
	uv python install $(PYTHON_VERSION)
	uv venv .venv --python $(PYTHON_VERSION)
	uv sync

playground:
	uv run --python $(PYTHON_VERSION) adk web app/agents

run:
	uv run --python $(PYTHON_VERSION) python -m app.agent

demo:
	uv run --python $(PYTHON_VERSION) python main.py

deploy:
	@echo "Deploying to Agent Engine in project $(PROJECT_ID)..."
	@echo "Ensuring staging bucket $(STAGING_BUCKET) exists..."
	gcloud storage buckets create $(STAGING_BUCKET) --project=$(PROJECT_ID) --location=$(REGION) || true
	
	@echo "Running official Starter Pack deployment CLI..."
	uv run --python $(PYTHON_VERSION) python -m app.app_utils.deploy \
		--project=$(PROJECT_ID) \
		--location=$(REGION) \
		--display-name="fleet-safety-agent" \
		--description="Multi-agent fleet safety system with route planning, risk monitoring, and analytics" \
		--entrypoint-module=app.agent_engine_app \
		--entrypoint-object=agent_engine \
		--env-file=.env

register-gemini-enterprise:
	@echo "Registering agent with Gemini Enterprise..."
	# Add registration logic here

test:
	uv run --python $(PYTHON_VERSION) pytest tests/

test-unit:
	uv run --python $(PYTHON_VERSION) pytest tests/unit/ -v

test-integration:
	uv run --python $(PYTHON_VERSION) pytest tests/integration/ -v

eval:
	uv run --python $(PYTHON_VERSION) adk eval \
		app/agents/fleet_safety \
		app/agents/fleet_safety/evaluation/comprehensive.evalset.json \
		--config_file_path=app/agents/fleet_safety/evaluation/comprehensive_config.json \
		--print_detailed_results

eval-all:
	./run_evals.sh

lint:
	uv run --python $(PYTHON_VERSION) ruff check .
	uv run --python $(PYTHON_VERSION) mypy .

setup-dev-env:
	gcloud services enable aiplatform.googleapis.com cloudbuild.googleapis.com storage.googleapis.com
	@echo "APIs enabled."

clean:
	rm -rf build dist .venv
