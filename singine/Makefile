.PHONY: help status smoke

help:
	@printf "singine/ package commands:\n"
	@printf "  make status  Show git status from the repo root\n"
	@printf "  make smoke   Compile the Python package to catch syntax errors\n"

status:
	git -C .. status -sb

smoke:
	python3 -m compileall .
