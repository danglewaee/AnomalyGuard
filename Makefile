.PHONY: up down logs ps build up-scale bench retrain backtest

up:
	docker compose -f infra/docker-compose/docker-compose.yml up --build -d

up-scale:
	docker compose -f infra/docker-compose/docker-compose.yml -f infra/docker-compose/docker-compose.scale.yml up --build -d

down:
	docker compose -f infra/docker-compose/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose/docker-compose.yml logs -f --tail=200

ps:
	docker compose -f infra/docker-compose/docker-compose.yml ps

build:
	docker compose -f infra/docker-compose/docker-compose.yml build

bench:
	python scripts/benchmark_baseline_vs_milp.py --limit 20 --traffic-multiplier 1.2 --output-json benchmark_report.json

retrain:
	python scripts/retrain_register.py --dsn postgresql://optimizer:optimizer@localhost:5432/optimizer

backtest:
	python scripts/backtest_rollout_policy.py --limit 10 --traffic-multiplier 1.2 --output-json rollout_backtest_report.json
