.PHONY: up down logs build test backend-test frontend-test safety-check verify-phase15 prod-up prod-down

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

backend-test:
	docker compose exec backend pytest -q

frontend-test:
	cd frontend && npm run test

safety-check:
	docker compose exec backend pytest tests/safety -q

verify-phase15:
	bash scripts/verify_phase15.sh

prod-up:
	docker compose -f docker-compose.prod.yml up -d --build

prod-down:
	docker compose -f docker-compose.prod.yml down
