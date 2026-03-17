.PHONY: help status list knowyourai

help:
	@printf "scenarios/ commands:\n"
	@printf "  make status  Show git status from the repo root\n"
	@printf "  make list    List scenario files\n"
	@printf "  make knowyourai List KnowYourAI query scenarios\n"

status:
	git -C .. status -sb

list:
	find . -maxdepth 4 -type f | sort

knowyourai:
	find ./knowyourai -maxdepth 2 -type f | sort
