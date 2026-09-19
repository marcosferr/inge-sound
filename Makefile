.PHONY: help install dev-api dev-web test lint build up down logs clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Instala las dependencias de backend y frontend
	cd backend && pip install -r requirements-dev.txt
	cd frontend && npm install

dev-api:  ## Levanta la API con recarga automática
	cd backend && uvicorn app.main:app --reload --port 8000

dev-web:  ## Levanta el frontend en modo desarrollo
	cd frontend && npm run dev

test:  ## Corre los tests del backend
	cd backend && pytest -q

lint:  ## Linter de Python y chequeo de tipos de TypeScript
	cd backend && ruff check .
	cd frontend && npx tsc --noEmit

build:  ## Compila el frontend para producción
	cd frontend && npm run build

up:  ## Levanta todo con Docker (CPU)
	docker compose up --build -d

down:  ## Baja los contenedores
	docker compose down

logs:  ## Sigue los logs
	docker compose logs -f

clean:  ## Borra artefactos de build y datos locales
	rm -rf backend/data backend/.pytest_cache backend/.ruff_cache frontend/dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
