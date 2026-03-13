.PHONY: help status list

help:
	@printf "scenarios/ commands:\n"
	@printf "  make status  Show git status from the repo root\n"
	@printf "  make list    List scenario files\n"

status:
	git -C .. status -sb

list:
	find . -maxdepth 4 -type f | sort
