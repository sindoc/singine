.PHONY: help status list

help:
	@printf "docs/ commands:\n"
	@printf "  make status  Show git status from the repo root\n"
	@printf "  make list    List documentation files in this directory\n"

status:
	git -C .. status -sb

list:
	find . -maxdepth 2 -type f | sort
