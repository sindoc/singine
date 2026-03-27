# singine/schema/Makefile — XProc 3.0 pipeline targets
# ─────────────────────────────────────────────────────
# Processor: XML Calabash 3.0.42 (Norman Walsh, XProc 3.0)
# XSLT:      Saxon-HE 12.9 (transitive dep, via Maven)
# Catalog:   xmlresolver 6.0.21 (OASIS XML Catalogs V1.1)
# Build:     Apache Maven 3.9+ (resolves all Calabash deps)
#
# Prerequisites
# ─────────────
#   brew install maven   (or: apt install maven)
#   Java 11+             (Java 21 recommended)
#
# Quick start
# ───────────
#   make help            show this help
#   make test            run hello.xpl smoke test
#   make validate        run vocab-validate.xpl
#   make report          alias for test (catalog-report output)
#   make deps            resolve + print Maven dependency tree
#   make clean           remove output/ directory
#   make all             deps + test + validate

SCHEMA_DIR  := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))
POM         := $(SCHEMA_DIR)pom.xml
CATALOG     := $(SCHEMA_DIR)catalog.xml
OUTPUT_DIR  := $(SCHEMA_DIR)output
MVN         := mvn
MVN_FLAGS   := -f $(POM) --no-transfer-progress

# Calabash invocation via Maven exec:exec
# Maven resolves com.xmlcalabash:app:3.0.42 and all transitive deps,
# then forks a JVM with the full classpath + catalog system properties.
CALABASH    := $(MVN) $(MVN_FLAGS) exec:java \
               -Dcatalog.file=$(CATALOG)

.PHONY: all help test validate report deps clean output-dir

# ── Default target ────────────────────────────────────────────────────
all: test validate

# ── Help ──────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "singine/schema — XProc 3.0 pipeline Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  test       Run hello.xpl smoke test (catalog report)"
	@echo "  validate   Run vocab-validate.xpl (schema + vocab)"
	@echo "  report     Alias for test"
	@echo "  deps       Resolve and print Maven dependency tree"
	@echo "  clean      Remove output/ directory"
	@echo "  all        deps + test + validate"
	@echo ""
	@echo "Processor: XML Calabash $(shell $(MVN) $(MVN_FLAGS) -q help:evaluate \
	  -Dexpression=calabash.version -DforceStdout 2>/dev/null || echo 3.0.42)"
	@echo "Catalog:   $(CATALOG)"
	@echo "Output:    $(OUTPUT_DIR)/"
	@echo ""

# ── Create output directory ───────────────────────────────────────────
output-dir:
	@mkdir -p $(OUTPUT_DIR)

# ── Smoke test: hello.xpl ─────────────────────────────────────────────
# Loads catalog.xml, applies XSLT 3.0 catalog-report.xsl,
# writes output/catalog-report.xml, emits to stdout.
test: output-dir
	@echo "── [singine] XProc 3.0 smoke test: hello.xpl ──────────────────"
	$(CALABASH) -Dpipeline=pipelines/hello.xpl
	@echo ""
	@echo "── Report written to: $(OUTPUT_DIR)/catalog-report.xml"
	@if [ -f $(OUTPUT_DIR)/catalog-report.xml ]; then \
	  echo "── Summary:"; \
	  grep -o 'count="[0-9]*"' $(OUTPUT_DIR)/catalog-report.xml | head -5 || true; \
	fi

# ── Vocabulary validation: vocab-validate.xpl ────────────────────────
# Tests that all key schema files (catalog.xml, singine.rnc, singine.sch,
# knowyourai.ttl) are loadable and well-formed.
validate: output-dir
	@echo "── [singine] XProc 3.0 validation: vocab-validate.xpl ─────────"
	$(CALABASH) -Dpipeline=pipelines/vocab-validate.xpl
	@echo ""
	@echo "── Report written to: $(OUTPUT_DIR)/validation-report.xml"
	@if [ -f $(OUTPUT_DIR)/validation-report.xml ]; then \
	  echo "── Results:"; \
	  grep -o 'status="[a-z]*"' $(OUTPUT_DIR)/validation-report.xml || true; \
	fi

# ── Alias for test ────────────────────────────────────────────────────
report: test

# ── Maven dependency tree ─────────────────────────────────────────────
deps:
	@echo "── [singine] Resolving Maven dependency tree ───────────────────"
	$(MVN) $(MVN_FLAGS) dependency:tree

# ── Clean ─────────────────────────────────────────────────────────────
clean:
	@echo "── [singine] Cleaning output/ ──────────────────────────────────"
	rm -rf $(OUTPUT_DIR)
	@echo "Done."
