DOCLET_XML := $(abspath ../core/target/javadoc-xml/doclet.xml)
SPEC_XML := $(abspath spec-publication.xml)
TARGET_DIR := target/spec
TARGET_CSS_DIR := $(TARGET_DIR)/css
SPEC_CSS_SRC := $(abspath ../../silkpage/docs/src/css/spec.css)
SILKPAGE_XSL := $(abspath ../../silkpage/docs/src/xsl/html-spec-single.xsl)
DOCLET_REF := $(TARGET_DIR)/singine-jvm-reference.xml
SPEC_DOC := $(TARGET_DIR)/singine-spec.xml
MAN_DEPS := $(TARGET_DIR)/manpage-dependencies.xml
SPEC_HTML := $(TARGET_DIR)/singine-spec.html

.PHONY: help status list knowyourai spec spec-ref spec-index spec-deps spec-html clean

help:
	@printf "docs/ commands:\n"
	@printf "  make status     Show git status from the repo root\n"
	@printf "  make list       List documentation files in this directory\n"
	@printf "  make knowyourai Show the KnowYourAI SPARQL guide path\n"
	@printf "  make spec       Generate spec XML artifacts from xmldoclet and the publication manifest\n"
	@printf "  make spec-html  Render the generated spec article through the SilkPage spec theme\n"

status:
	git -C .. status -sb

list:
	find . -maxdepth 3 -type f | sort

knowyourai:
	@printf "%s\n" "$$(pwd)/knowyourai-sparql.md"

$(TARGET_DIR):
	mkdir -p $(TARGET_DIR)

$(TARGET_CSS_DIR):
	mkdir -p $(TARGET_CSS_DIR)

spec-ref: $(TARGET_DIR)
	xsltproc xsl/spec-doclet-to-docbook.xsl $(DOCLET_XML) > $(DOCLET_REF)

spec-index: $(TARGET_DIR)
	xsltproc --stringparam doclet.path $(DOCLET_XML) xsl/spec-manifest-to-docbook.xsl $(SPEC_XML) > $(SPEC_DOC)

spec-deps: $(TARGET_DIR)
	xsltproc xsl/spec-manifest-deps.xsl $(SPEC_XML) > $(MAN_DEPS)

spec: spec-ref spec-index spec-deps

spec-html: spec-index $(TARGET_CSS_DIR)
	cp $(SPEC_CSS_SRC) $(TARGET_CSS_DIR)/spec.css
	xsltproc --stringparam www.root "" --stringparam html.stylesheet css/spec.css $(SILKPAGE_XSL) $(SPEC_DOC) > $(SPEC_HTML)

clean:
	rm -rf $(TARGET_DIR)
