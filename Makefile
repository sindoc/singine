.PHONY: help status test test-core serve-core repl-core javac-core python-smoke backlog-status

help:
	@printf "Singine commands:\n"
	@printf "  make status        Show repo status\n"
	@printf "  make test          Run the core tests and a Python compile smoke test\n"
	@printf "  make test-core     Run Clojure tests in core/\n"
	@printf "  make serve-core    Start the local Clojure server from core/\n"
	@printf "  make repl-core     Open the Clojure REPL in core/\n"
	@printf "  make javac-core    Compile Java helpers into core/classes/\n"
	@printf "  make python-smoke  Compile the Python package to catch syntax errors\n"
	@printf "  make backlog-status Show backlog repo status\n"

status:
	git status -sb

test: test-core python-smoke

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

backlog-status:
	git -C /Users/skh/ws/git/local/backlog status -sb
