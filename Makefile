COMPOSE = docker compose -f docker-compose.hw8.yml
PYTHON ?= python

.PHONY: up-hw08 down-hw08 ps-hw08 logs-hw08 test-hw08 verify-hw08 api-quiet-hw08 api-verbose-hw08

up-hw08:
	mkdir -p reports/hw08/raw
	$(COMPOSE) up -d --build

down-hw08:
	$(COMPOSE) down

ps-hw08:
	$(COMPOSE) ps

logs-hw08:
	$(COMPOSE) logs --tail=40 worker api

test-hw08:
	$(PYTHON) -m pytest -q test_hw8_part1_offline.py test_hw8_agents_offline.py test_hw8_failure_scenarios_offline.py test_hw8_tools_offline.py

verify-hw08:
	$(PYTHON) verify_hw08.py

# JMeter runs: turn the API console logging off, then back on for the demos.
api-quiet-hw08:
	HW8_API_VERBOSE=0 $(COMPOSE) up -d api

api-verbose-hw08:
	HW8_API_VERBOSE=1 $(COMPOSE) up -d api

# ---------------------------------------------------------------- HW9
.PHONY: up-hw09 down-hw09 test-hw09 verify-hw09 part1-hw09 part2-hw09 part3-hw09 part4-hw09

up-hw09:
	mkdir -p reports/hw09/raw
	docker compose -f docker-compose.hw9.yml up -d

down-hw09:
	docker compose -f docker-compose.hw9.yml down

test-hw09:
	$(PYTHON) -m pytest -q test_hw9_offline.py

verify-hw09:
	$(PYTHON) verify_hw09.py

part1-hw09:
	$(PYTHON) demo_hw09_part1.py

part2-hw09:
	$(PYTHON) run_hw09_part2.py

part3-hw09:
	$(PYTHON) run_hw09_part3.py agents
	$(PYTHON) run_hw09_part3.py sweep
	$(PYTHON) run_hw09_part3.py falsehit
	$(PYTHON) run_hw09_part3.py stale

part4-hw09:
	$(PYTHON) run_hw09_part4.py demo-revision
	$(PYTHON) run_hw09_part4.py train
	$(PYTHON) run_hw09_part4.py validate
	$(PYTHON) run_hw09_part4.py demo-reuse
	$(PYTHON) run_hw09_part4.py final
