SINGINE_CORTEX_DB      ?= /tmp/sqlite.db
SINGINE_DOMAIN_DB      ?= /tmp/humble-idp.db
SINGINE_KERNEL_GRAPH   ?= $(HOME)/ws/logseq/singine/sindoc/fa-KfK-HDYAT-KRNL-421b
SINGINE_KERNEL_SEARCH  ?= singine
SINGINE_REF            ?= C12
HUMBLE_IDP_JAVA        ?= $(HOME)/ws/today/cleanUp/X0-DigitalIdentity/humble-idp/java

.PHONY: help status test test-core serve-core repl-core javac-core python-smoke py-test-xml py-test-transfer-flow py-test-multilingual-emotion py-test-photo py-test-surface py-test-domain backlog-status install install-bash install-sh manpath bridge-build bridge-sources xml-matrix knowyourai-list knowyourai-query auth-demo auth-uri auth-code model-catalog brew-clojure transfer-queue-demo transfer-stack-demo logseq-kernel-build logseq-kernel-sources logseq-kernel-search logseq-kernel-commit logseq-kernel-sync domain-schema domain-seed domain-event-log domain-tx-list domain-refdata-list domain-docs docs

help:
	@printf "Singine commands:\n"
	@printf "  make status        Show repo status\n"
	@printf "  make test          Run the core tests and a Python compile smoke test\n"
	@printf "  make test-core     Run Clojure tests in core/\n"
	@printf "  make serve-core    Start the local Clojure server from core/\n"
	@printf "  make repl-core     Open the Clojure REPL in core/\n"
	@printf "  make javac-core    Compile Java helpers into core/classes/\n"
	@printf "  make python-smoke  Compile the Python package to catch syntax errors\n"
	@printf "  make py-test-xml   Run the XML matrix Python test\n"
	@printf "  make py-test-multilingual-emotion  Run the multilingual emotion bundle test\n"
	@printf "  make py-test-photo Run the singine photo workflow test suite\n"
	@printf "  make py-test-surface Run the mock server/logseq surface integration test\n"
	@printf "  make install       Install singine into ~/.local for sh\n"
	@printf "  make install-bash  Install singine into ~/.local for bash\n"
	@printf "  make install-sh    Install singine into ~/.local for sh\n"
	@printf "  make manpath       Show local manpage path\n"
	@printf "  make backlog-status Show backlog repo status\n"
	@printf "  make bridge-build  Build the local SQLite bridge database\n"
	@printf "  make bridge-sources List bridge sources from the local database\n"
	@printf "  make xml-matrix    Generate XML request/response/heatmap artifacts\n"
	@printf "  make knowyourai-list List bundled KnowYourAI SPARQL query files\n"
	@printf "  make knowyourai-query QUERY=... Run a bundled KnowYourAI SPARQL query file\n"
	@printf "  make auth-demo     Create a local demo TOTP profile under /tmp\n"
	@printf "  make auth-uri      Print the demo otpauth URI\n"
	@printf "  make auth-code     Print the current demo one-time code\n"
	@printf "  make model-catalog Show Singine model objects and bridge types\n"
	@printf "  make brew-clojure      Install Clojure CLI via Homebrew\n"
	@printf "  make py-test-transfer-flow  Run the Flowable transfer test suite\n"
	@printf "  make transfer-queue-demo    Demo queue push/list/pop\n"
	@printf "  make transfer-stack-demo  Demo stack push/list/pop\n"
	@printf "  make logseq-kernel-build   Build bridge from fa-KfK-HDYAT-KRNL-421b kernel\n"
	@printf "  make logseq-kernel-sources List bridge sources (kernel view)\n"
	@printf "  make logseq-kernel-search  SINGINE_KERNEL_SEARCH=<term> Search kernel bridge\n"
	@printf "  make logseq-kernel-commit  Git-commit new kernel journals (ref SINGINE_REF)\n"
	@printf "  make logseq-kernel-sync    Rebuild bridge after Logseq Sync drop\n"
	@printf "  make domain-schema         Init Humble IDP SQLite schema (SINGINE_DOMAIN_DB)\n"
	@printf "  make domain-seed           Seed electricity balancing master data and ref data\n"
	@printf "  make domain-event-log      Show recent domain events\n"
	@printf "  make domain-tx-list        List governed transactions\n"
	@printf "  make domain-refdata-list   List reference data code sets\n"
	@printf "  make domain-docs           Build DocBook + Javadoc HTML for Humble IDP\n"
	@printf "  make docs                  Build all Singine + Humble IDP documentation\n"
	@printf "  make py-test-domain        Run domain command Python tests\n"

status:
	git status -sb

test: test-core python-smoke py-test-transfer-flow py-test-multilingual-emotion py-test-photo py-test-surface py-test-domain

test-core:
	$(MAKE) -C core test

serve-core:
	$(MAKE) -C core serve

repl-core:
	$(MAKE) -C core repl

javac-core:
	$(MAKE) -C core javac

python-smoke:
	python3 -m compileall singine
	python3 -m py_compile setup.py

py-test-xml:
	python3 -m unittest py.tests.test_xml_matrix

py-test-transfer-flow:
	python3 -m unittest py.tests.test_transfer_flow -v

py-test-multilingual-emotion:
	python3 -m unittest py.tests.test_multilingual_emotion_bundle -v

py-test-photo:
	python3 -m unittest py.tests.test_photo -v

py-test-surface:
	python3 -m unittest py.tests.test_server_surface_commands -v

py-test-domain:
	python3 -m unittest py.tests.test_domain_commands -v

install:
	python3 -m singine.command install --prefix "$$HOME/.local" --shell all

install-bash:
	python3 -m singine.command install --prefix "$$HOME/.local" --shell bash

install-sh:
	python3 -m singine.command install --prefix "$$HOME/.local" --shell sh

manpath:
	@printf "%s\n" "$$HOME/.local/share/man"

backlog-status:
	git -C /Users/skh/ws/git/local/backlog status -sb

bridge-build:
	python3 -m singine.command bridge build --db "$${SINGINE_CORTEX_DB:-/tmp/sqlite.db}"

bridge-sources:
	python3 -m singine.command bridge sources --db "$${SINGINE_CORTEX_DB:-/tmp/sqlite.db}"

xml-matrix:
	python3 -m singine.command xml matrix --db "$${SINGINE_CORTEX_DB:-/tmp/sqlite.db}" --output-dir /tmp/singine-xml-matrix

knowyourai-list:
	find scenarios/knowyourai -maxdepth 1 -name '*.rq' -type f | sort

knowyourai-query:
	@test -n "$(QUERY)" || { printf "Set QUERY=scenarios/knowyourai/<name>.rq\n" >&2; exit 1; }
	python3 -m singine.command bridge sparql --db "$${SINGINE_CORTEX_DB:-/tmp/sqlite.db}" "$$(tr '\n' ' ' < "$(QUERY)")"

auth-demo:
	python3 -m singine.command auth totp init --issuer Singine --account-name demo@singine.local --provider 1password --state /tmp/singine-totp.json

auth-uri:
	python3 -m singine.command auth totp uri --state /tmp/singine-totp.json --json

auth-code:
	python3 -m singine.command auth totp code --state /tmp/singine-totp.json --json

model-catalog:
	python3 -m singine.command model catalog

brew-clojure:
	brew install clojure/tools/clojure

transfer-queue-demo:
	python3 -m singine.command transfer queue push "item-a"
	python3 -m singine.command transfer queue push "item-b"
	python3 -m singine.command transfer queue list
	python3 -m singine.command transfer queue pop

transfer-stack-demo:
	python3 -m singine.command transfer stack push "item-a"
	python3 -m singine.command transfer stack push "item-b"
	python3 -m singine.command transfer stack list
	python3 -m singine.command transfer stack pop

# ── Domain layer (Humble IDP SQLite) ─────────────────────────────────────────
# Override: make domain-schema SINGINE_DOMAIN_DB=/path/to/db.sqlite

domain-schema:
	python3 -m singine.command domain schema init --db "$(SINGINE_DOMAIN_DB)"
	python3 -m singine.command domain schema tables --db "$(SINGINE_DOMAIN_DB)"

domain-seed: domain-schema
	python3 -m singine.command domain master add --type BusinessTerm \
	  --name "Electricity Balancing" --collibra-id "" --db "$(SINGINE_DOMAIN_DB)"
	python3 -m singine.command domain master add --type BusinessCapability \
	  --name "Grid Operations" --db "$(SINGINE_DOMAIN_DB)"
	python3 -m singine.command domain master add --type BusinessProcess \
	  --name "Electricity Balancing Process" --db "$(SINGINE_DOMAIN_DB)"
	python3 -m singine.command domain master add --type DataCategory \
	  --name "Energy Data" --db "$(SINGINE_DOMAIN_DB)"
	python3 -m singine.command domain refdata add --code-set scenario-codes \
	  --code ELBA --label "Electricity Balancing" --db "$(SINGINE_DOMAIN_DB)"
	python3 -m singine.command domain refdata add --code-set iata-codes \
	  --code BRU --label "Brussels Airport" --db "$(SINGINE_DOMAIN_DB)"

domain-event-log:
	python3 -m singine.command domain event log --limit 20 --db "$(SINGINE_DOMAIN_DB)"

domain-tx-list:
	python3 -m singine.command domain tx list --db "$(SINGINE_DOMAIN_DB)"

domain-refdata-list:
	python3 -m singine.command domain refdata list --db "$(SINGINE_DOMAIN_DB)"

domain-docs:
	$(MAKE) -C "$(HUMBLE_IDP_JAVA)" docs

docs: domain-docs
	@printf "All documentation built.\n"

# ── Logseq kernel (fa-KfK-HDYAT-KRNL-421b) ──────────────────────────────────
# Override: make logseq-kernel-search SINGINE_KERNEL_SEARCH="smtp"
#           make logseq-kernel-commit SINGINE_REF=C13

logseq-kernel-build:
	SINGINE_LOGSEQ_GRAPH="$(SINGINE_KERNEL_GRAPH)" \
	  python3 -m singine.command bridge build --db "$(SINGINE_CORTEX_DB)"

logseq-kernel-sources:
	python3 -m singine.command bridge sources --db "$(SINGINE_CORTEX_DB)"

logseq-kernel-search:
	python3 -m singine.command bridge search --db "$(SINGINE_CORTEX_DB)" \
	  "$(SINGINE_KERNEL_SEARCH)"

logseq-kernel-commit:
	git -C "$(SINGINE_KERNEL_GRAPH)" add journals/
	git -C "$(SINGINE_KERNEL_GRAPH)" diff --cached --stat
	git -C "$(SINGINE_KERNEL_GRAPH)" commit -m \
	  "ref($(SINGINE_REF)): journal sync $$(date +%Y-%m-%d)" \
	  --allow-empty-message

logseq-kernel-sync: logseq-kernel-build logseq-kernel-sources
	@printf "kernel bridge rebuilt from %s\n" "$(SINGINE_KERNEL_GRAPH)"
