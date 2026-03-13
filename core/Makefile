.PHONY: help status test serve repl javac

help:
	@printf "core/ commands:\n"
	@printf "  make status  Show git status from the repo root\n"
	@printf "  make test    Run the Clojure test suite\n"
	@printf "  make serve   Start the local server\n"
	@printf "  make repl    Open the development REPL\n"
	@printf "  make javac   Compile Java helpers into classes/\n"

status:
	git -C .. status -sb

test:
	clojure -M:test

serve:
	clojure -M:serve

repl:
	clojure -M:repl

javac:
	clojure -M:javac
