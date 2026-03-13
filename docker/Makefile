.PHONY: help status edge-up edge-down mail-up mail-down

help:
	@printf "docker/ commands:\n"
	@printf "  make status    Show git status from the repo root\n"
	@printf "  make edge-up   Start the edge stack\n"
	@printf "  make edge-down Stop the edge stack\n"
	@printf "  make mail-up   Start the mail stack\n"
	@printf "  make mail-down Stop the mail stack\n"

status:
	git -C .. status -sb

edge-up:
	docker compose -f docker-compose.edge.yml up -d

edge-down:
	docker compose -f docker-compose.edge.yml down

mail-up:
	docker compose -f docker-compose.mail.yml up -d

mail-down:
	docker compose -f docker-compose.mail.yml down
