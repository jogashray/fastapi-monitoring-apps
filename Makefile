.PHONY: install run test up down logs smoke load clean

install:
	pip install -r requirements.txt

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest -v

up:
	docker-compose up -d --build
	@echo "Services starting..."
	@echo "App:        http://localhost:8000"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana:    http://localhost:3000  (admin/admin)"
	@echo "Alertmgr:   http://localhost:9093"

down:
	docker-compose down

logs:
	docker-compose logs -f

smoke:
	bash scripts/smoke_test.sh

# Generate synthetic traffic to populate Grafana dashboards.
# Runs INSIDE the FastAPI container so you don't need httpx
# installed on your host. Defaults: 1500 mixed GET/POST requests
# with ~5% error rate.
# Override:  make load COUNT=2000 CONCURRENCY=8
load:
	docker-compose exec -T app python /code/scripts/generate_traffic.py \
		--count $(or $(COUNT),1500) \
		--concurrency $(or $(CONCURRENCY),4) \
		--base-url http://localhost:8000

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/