SINGINE_KERNEL_SEARCH ?= singine
SINGINE_REF           ?= C12

.PHONY: help status edge-up edge-down mail-up mail-down \
        kernel-build kernel-sources kernel-search kernel-sync kernel-down

help:
	@printf "docker/ commands:\n"
	@printf "  make status                         Show git status from the repo root\n"
	@printf "  make edge-up                        Start the edge stack\n"
	@printf "  make edge-down                      Stop the edge stack\n"
	@printf "  make mail-up                        Start the mail stack\n"
	@printf "  make mail-down                      Stop the mail stack\n"
	@printf "  make kernel-build                   Build kernel bridge (docker)\n"
	@printf "  make kernel-sources                 List kernel bridge sources (docker)\n"
	@printf "  make kernel-search SINGINE_KERNEL_SEARCH=<term>  Search kernel (docker)\n"
	@printf "  make kernel-sync                    Build + sources in one shot (docker)\n"
	@printf "  make kernel-down                    Stop and remove kernel containers\n"

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

# ── kernel bridge (fa-KfK-HDYAT-KRNL-421b) ──────────────────────────────────

kernel-build:
	SINGINE_REF="$(SINGINE_REF)" \
	  docker compose -f docker-compose.kernel.yml run --rm kernel-build

kernel-sources:
	docker compose -f docker-compose.kernel.yml run --rm kernel-sources

kernel-search:
	SINGINE_KERNEL_SEARCH="$(SINGINE_KERNEL_SEARCH)" \
	  docker compose -f docker-compose.kernel.yml run --rm kernel-search

kernel-sync:
	SINGINE_REF="$(SINGINE_REF)" \
	  docker compose -f docker-compose.kernel.yml run --rm kernel-sync

kernel-down:
	docker compose -f docker-compose.kernel.yml down --remove-orphans
