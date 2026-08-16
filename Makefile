# =====================================================================
# PARK It Up Acquisition Intelligence
#
# Self-documenting entry points. `make help` lists everything.
# Variables come from .env where present, so no credentials live here.
# =====================================================================

SHELL := /bin/bash
PSQL  := psql -v ON_ERROR_STOP=1
DB    ?= $(or $(PGDATABASE),parkitup)

SCHEMA_FILES := database/schema/00_init.sql \
                database/schema/01_reference.sql \
                database/schema/02_core_entities.sql \
                database/schema/03_facts.sql \
                database/schema/04_bd_pipeline.sql \
                database/schema/05_scoring.sql \
                database/schema/06_analysis.sql

SEED_FILES   := database/seeds/01_seed_reference.sql \
                database/seeds/02_seed_calendar.sql

.DEFAULT_GOAL := help
.PHONY: help venv validate-ddl validate-schema db-create db-build db-seed db-reset data-source scrub-sources data-build data-load pipeline score analytics-views analytics-test validate notebooks validate-all powerbi-data powerbi-pages powerbi dashboard audit dq test clean

help: ## Show this help
	@echo "PARK It Up Acquisition Intelligence"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Current target database: $(DB)"

venv: ## Create a virtual environment and install dependencies
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -r requirements.txt
	@echo "Activate with: source .venv/bin/activate"

validate-ddl: ## Structural DDL checks (no database required)
	python3 python/etl/validate_ddl.py

validate-schema: ## Full validation against a real PostgreSQL server
	bash scripts/validate_schema.sh

db-create: ## Create the project database (safe if it already exists)
	-createdb $(DB)

db-build: db-create ## Apply the schema to $(DB)
	@for f in $(SCHEMA_FILES); do echo "-> $$f"; $(PSQL) -d $(DB) -f $$f || exit 1; done

db-seed: ## Apply reference and calendar seeds to $(DB)
	@for f in $(SEED_FILES); do echo "-> $$f"; $(PSQL) -d $(DB) -f $$f || exit 1; done

db-reset: ## DESTRUCTIVE. Drop all project tables, then rebuild and reseed
	$(PSQL) -d $(DB) -f database/schema/99_drop_all.sql
	$(MAKE) db-build db-seed

data-source: ## Refresh and cache the public OSM source snapshot
	./.venv/bin/python python/etl/source_collection.py --refresh

scrub-sources: ## Strip personal-contact tags from the cached OSM snapshot, in place
	./.venv/bin/python python/etl/source_collection.py --scrub-cache

data-build: ## Build the raw and processed datasets from the local source cache
	./.venv/bin/python python/etl/build_dataset.py

data-load: ## Load the processed datasets into PostgreSQL
	./.venv/bin/python python/etl/build_dataset.py --load-postgres --no-build

pipeline: db-build db-seed ## Run the complete cached ETL, PostgreSQL load, and validation pipeline
	./.venv/bin/python python/etl/build_dataset.py --load-postgres

score: ## Build, persist, validate and document the acquisition scoring engine
	./.venv/bin/python python/analysis/scoring_engine.py

analytics-views: ## Install the reusable SQL analytics views
	$(PSQL) -d $(DB) -f database/views/01_analytics_views.sql

analytics-test: analytics-views ## Install the analytics views and run their assertions
	$(PSQL) -d $(DB) -f sql/tests/analytics_assertions.sql

validate: ## Run EDA, model validation, sensitivity analysis, charts and exports
	./.venv/bin/python python/analysis/run_validation.py

notebooks: ## Execute the four analytical notebooks in place
	@for f in python/notebooks/0*.ipynb; do echo "-> $$f"; ./.venv/bin/jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=600 "$$f" || exit 1; done

validate-all: validate notebooks ## Run the complete validation layer

powerbi-data: ## Prepare and reconcile the portable Power BI star-schema extracts
	./.venv/bin/python python/analysis/prepare_powerbi.py

powerbi-pages: powerbi-data ## Generate five actual-data Power BI design previews
	./.venv/bin/python python/visualization/powerbi_mockups.py

powerbi: powerbi-data powerbi-pages ## Build the complete Power BI package

dashboard: powerbi-pages ## Regenerate, audit and validate the five-page dashboard previews
	./.venv/bin/python python/visualization/layout_audit.py
	./.venv/bin/python -m pytest tests/test_dashboard.py -q

dq: ## Run the data-quality rule catalogue against $(DB)
	$(PSQL) -d $(DB) -f sql/data_quality/dq_checks.sql

audit: ## Full database audit. Add ARGS=--reset to rebuild from a clean schema first
	bash scripts/audit.sh $(ARGS)

test: ## Run the Python test suite
	# The venv interpreter, not system python3: sqlalchemy and psycopg are
	# declared dependencies and are only installed there. Using python3 here
	# aborted collection with ModuleNotFoundError on a machine whose default
	# python3 is a pyenv build.
	./.venv/bin/python -m pytest tests/ -v

clean: ## Remove generated data, caches and validation output
	rm -rf __pycache__ .pytest_cache
	find . -name '*.pyc' -delete
	find data/raw data/processed -type f ! -name '.gitkeep' -delete
	find validation -type f ! -name '.gitkeep' -delete
