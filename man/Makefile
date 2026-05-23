MAN_DB          ?= $(REPO_ROOT)/data/singine-man.db
REPO_ROOT       ?= $(shell cd .. && pwd)
SILKPAGE_ROOT   ?= $(REPO_ROOT)/../silkpage/templates/site/default/src/xml/en
CLEANUP_SILKPAGE ?= $(REPO_ROOT)/cleanup/silkpage/src/xml/en
PG_URL          ?= postgresql://localhost:5432/singine
PYTHON          ?= python3

.PHONY: help seed generate migrate flc-list flc-show citizen-register clean all

help:
	@printf "Man page pipeline targets:\n"
	@printf "  make seed             Parse silkpage XML → SQLite sidebar entries\n"
	@printf "  make generate         SQLite lookup → roff .1 man pages\n"
	@printf "  make migrate          Emit SQLite→PostgreSQL INSERT statements\n"
	@printf "  make flc-list         List FLC assets in DB\n"
	@printf "  make flc-show FLC=MANP Show a single FLC code\n"
	@printf "  make citizen-register CID=<id> LABEL='...'  Register a data citizen\n"
	@printf "  make all              seed + generate\n"
	@printf "\nOptions (override via env or make args):\n"
	@printf "  MAN_DB=$(MAN_DB)\n"
	@printf "  SILKPAGE_ROOT=$(SILKPAGE_ROOT)\n"
	@printf "  PG_URL=$(PG_URL)\n"

all: seed generate

seed:
	$(PYTHON) generate_man.py seed \
	  --silkpage-root "$(SILKPAGE_ROOT)" \
	  --db "$(MAN_DB)"
	@if [ -d "$(CLEANUP_SILKPAGE)" ]; then \
	  $(PYTHON) generate_man.py seed \
	    --silkpage-root "$(CLEANUP_SILKPAGE)" \
	    --db "$(MAN_DB)"; \
	fi

generate:
	$(PYTHON) generate_man.py generate \
	  --page all \
	  --db "$(MAN_DB)" \
	  --out-dir "$(CURDIR)"

migrate:
	$(PYTHON) generate_man.py migrate \
	  --db "$(MAN_DB)" \
	  --pg-url "$(PG_URL)"

flc-list:
	$(PYTHON) generate_man.py flc list --db "$(MAN_DB)"

flc-show:
	$(PYTHON) generate_man.py flc show "$(FLC)" --db "$(MAN_DB)"

citizen-register:
	$(PYTHON) generate_man.py citizen register "$(CID)" \
	  --label "$(LABEL)" \
	  --community "$(COMMUNITY)" \
	  --db "$(MAN_DB)"

clean:
	rm -f singine-generated-*.1
