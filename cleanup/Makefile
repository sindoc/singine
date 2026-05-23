# cleanup/Makefile
# Builds the C stat-hook and Go scanner, then generates the initial report.
#
# Targets:
#   make all         — build everything
#   make scanner     — build Go scanner only (bin/scan)
#   make hook        — build C stat-hook only (bin/stat-hook)
#   make report      — run scanner → report/latest.json + report/cleanup.xml
#   make committee   — collect both result sets → report/committee-report.html
#   make atom        — generate output/latest/ATOM from committee-results.json
#   make silkpage    — transform report/cleanup.xml → output/cleanup.html via silkpage
#   make serve       — install nginx config and reload
#   make clean       — remove build artefacts

SCRIPT_DIR  := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
BIN_DIR     := $(SCRIPT_DIR)/bin
REPORT_DIR  := $(SCRIPT_DIR)/report
OUTPUT_DIR  := $(SCRIPT_DIR)/output
SCANNER     := $(BIN_DIR)/scan
HOOK        := $(BIN_DIR)/stat-hook
CDN_HOST    ?= cdn.example.org
SITE_PORT   ?= 8090

.PHONY: all scanner hook report committee atom silkpage serve clean

all: scanner hook report

# ── Go scanner ───────────────────────────────────────────────────────────────
scanner: $(SCANNER)

$(SCANNER): go/scanner/main.go go/scanner/go.mod
	@mkdir -p $(BIN_DIR)
	cd go/scanner && CGO_ENABLED=0 go build -trimpath -o $(SCANNER) .
	@echo "  [go]  $(SCANNER)"

# ── C stat-hook ──────────────────────────────────────────────────────────────
hook: $(HOOK)

$(HOOK): c/stat_hook.c
	$(MAKE) -C c/

# ── Report ───────────────────────────────────────────────────────────────────
report: $(SCANNER)
	@mkdir -p $(REPORT_DIR)
	$(SCANNER) --pretty true \
	           --out $(REPORT_DIR)/latest.json \
	           --xml $(REPORT_DIR)/cleanup.xml
	@echo "  [report] written to $(REPORT_DIR)/"

# ── Committee report ─────────────────────────────────────────────────────────
committee:
	@mkdir -p $(REPORT_DIR)
	python3 collect.py --out $(REPORT_DIR)/committee-results.json
	python3 render_committee.py \
	  --in  $(REPORT_DIR)/committee-results.json \
	  --out $(REPORT_DIR)/committee-report.html
	@echo "  [committee] $(REPORT_DIR)/committee-report.html"

# ── Atom feed ────────────────────────────────────────────────────────────────
atom: $(REPORT_DIR)/committee-results.json
	@mkdir -p $(OUTPUT_DIR)/latest
	python3 generate_atom.py \
	  --in  $(REPORT_DIR)/committee-results.json \
	  --out $(OUTPUT_DIR)/latest/ATOM \
	  --base-url https://singine.uk
	@echo "  [atom] $(OUTPUT_DIR)/latest/ATOM → https://singine.uk/latest/ATOM"

# ── silkpage transform → HTML ─────────────────────────────────────────────────
# Requires silkpage CLI on PATH: npm install -g silkpage
silkpage: $(REPORT_DIR)/cleanup.xml
	@mkdir -p $(OUTPUT_DIR)
	@if command -v silkpage >/dev/null 2>&1; then \
	  silkpage build \
	    --src  silkpage/src/xml/en/cleanup.xml \
	    --xsl  silkpage/src/xsl/cleanup.xsl \
	    --out  $(OUTPUT_DIR)/cleanup.html \
	    --param cdn=//$(CDN_HOST) \
	    --param report.xml=$(REPORT_DIR)/cleanup.xml; \
	  echo "  [silkpage] $(OUTPUT_DIR)/cleanup.html"; \
	else \
	  echo "  [silkpage] silkpage not found — run: npm install -g silkpage"; \
	fi

# ── Nginx ─────────────────────────────────────────────────────────────────────
serve:
	SILKPAGE_ROOT=$(SCRIPT_DIR) CDN_HOST=$(CDN_HOST) SITE_PORT=$(SITE_PORT) \
	REPORT_DIR=$(REPORT_DIR) \
	  envsubst '$$SILKPAGE_ROOT $$CDN_HOST $$SITE_PORT $$REPORT_DIR' \
	  < nginx/silkpage.conf \
	  | tee /tmp/cleanup-silkpage.conf
	@echo ""
	@echo "  Review /tmp/cleanup-silkpage.conf then:"
	@echo "  sudo cp /tmp/cleanup-silkpage.conf /etc/nginx/conf.d/"
	@echo "  sudo nginx -t && sudo nginx -s reload"

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	rm -f $(SCANNER) $(HOOK)
	rm -rf $(REPORT_DIR)/latest.json $(REPORT_DIR)/cleanup.xml
	rm -rf $(OUTPUT_DIR)
