SHELL := /bin/bash
.PHONY: setup reset apply-patches create-links venv help

# Root of the repo (where this Makefile lives)
ROOT := $(shell pwd)

# All submodule paths (extracted from .gitmodules)
SUBMODULES := $(shell git config --file .gitmodules --get-regexp path | awk '{print $$2}')

# All patch files under patches/
PATCHES := $(shell find patches -name '*.patch' 2>/dev/null)

# Python virtual environment
VENV := .pyenv

# =============================================================================

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-12s %s\n", $$1, $$2}'

# =============================================================================

reset: ## Reset all submodules to their committed state
	@echo "=== Resetting submodules ==="
	git submodule deinit -f --all
	git submodule update --init --recursive
	@echo ""
	@echo "All submodules restored to committed revisions."

# =============================================================================

setup: reset create-links apply-patches ## Full setup: reset + symlinks + patches
	@echo ""
	@echo "=== Setup complete ==="

# =============================================================================

create-links: ## Create symlinks required by the project
	@echo ""
	@echo "=== Creating symlinks ==="
	mkdir -p projects/sel4test/apps
	ln -sfn ../../../fglbench projects/sel4test/apps/fglbench
	ln -sfn ../../../benchset projects/sel4test/apps/benchset
	@echo "  projects/sel4test/apps/fglbench -> ../../../fglbench"
	@echo "  projects/sel4test/apps/benchset -> ../../../benchset"


# =============================================================================

apply-patches: ## Apply all patches under patches/ to their matching submodules
	@echo ""
	@echo "=== Applying patches ==="
	@for patch in $(PATCHES); do \
		target_dir=$$(dirname "$${patch#patches/}"); \
		echo "  $$patch -> $$target_dir"; \
		git -C "$$target_dir" am --quiet "$(ROOT)/$$patch" || \
		{ echo "ERROR: failed to apply $$patch"; exit 1; }; \
	done
	@echo "  $(words $(PATCHES)) patch(es) applied."

# =============================================================================

venv: ## Create Python venv and print activation command
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip setuptools
	$(VENV)/bin/pip install setuptools sel4-deps
	@[ -f requirements.txt ] && $(VENV)/bin/pip install -r requirements.txt || true
	@echo ""
	@echo "=== venv ready ==="
	@echo "  Run:  source $(VENV)/bin/activate"
