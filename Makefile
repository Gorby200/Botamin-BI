.PHONY: build dev pipeline frontend clean

SHEET ?=

build: ## Full build: pipeline + frontend → dist/
	@echo "Building Botamin BI..."
	@bash build.sh --sheet "$(SHEET)"

pipeline: ## Run Python pipeline only
	@source .venv/Scripts/activate && \
	PYTHONUTF8=1 python -W ignore -m pipeline --sheet "$(SHEET)" --out frontend/public/data

pipeline-file: ## Run pipeline with local file
	@source .venv/Scripts/activate && \
	PYTHONUTF8=1 python -W ignore -m pipeline --file "$(FILE)" --out frontend/public/data

frontend: ## Build React frontend only
	cd frontend && npm ci --legacy-peer-deps && npm run build

dev: ## Start dev server (run pipeline first)
	cd frontend && npm run dev

clean: ## Clean all generated files
	rm -rf frontend/dist frontend/public/data/calls/*.json
	rm -f frontend/public/data/dashboard.json frontend/public/data/backlog.json
	rm -f data/raw.csv

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
