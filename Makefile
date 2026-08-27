# Ombor CRM — qisqa komandalar.
#
#   make            -> ro'yxatni ko'rsatadi
#   make run        -> lokal server
#   make test       -> barcha testlar
#   make up         -> serverda docker bilan ishga tushirish
#
# Windows'da `make` bo'lmasa: Git Bash uchun choco/scoop orqali o'rnatiladi,
# yoki har bir komandaning ichidagi qatorni qo'lda ishlating.

# Virtual muhit qayerda bo'lsa — o'shani topadi (Windows / Linux)
PYTHON ?= $(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,$(if $(wildcard .venv/bin/python),.venv/bin/python,python3))
MANAGE := $(PYTHON) manage.py
CADDY_NETWORK := $(shell [ -f .env ] && grep -E '^CADDY_NETWORK=' .env | cut -d= -f2)
COMPOSE := docker compose $(if $(CADDY_NETWORK),-f docker-compose.yml -f docker-compose.caddy.yml,)
DOMAIN := ombor.thesofmebel.uz
BACKUP_DIR ?= /var/backups

.DEFAULT_GOAL := help

# ----------------------------------------------------------------- lokal ish

.PHONY: help
help: ## Shu ro'yxatni ko'rsatadi
	@echo "Ombor CRM — komandalar:"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo

.PHONY: install
install: ## Kutubxonalarni o'rnatadi
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

.PHONY: run
run: ## Lokal serverni ishga tushiradi (127.0.0.1:8000)
	$(MANAGE) runserver

.PHONY: migrations
migrations: ## Yangi migratsiya yozadi
	$(MANAGE) makemigrations

.PHONY: migrate
migrate: ## Migratsiyalarni bazaga qo'llaydi
	$(MANAGE) migrate

.PHONY: superuser
superuser: ## Admin foydalanuvchi ochadi
	$(MANAGE) createsuperuser

.PHONY: seed
seed: ## Kassa yacheykalarini yaratadi
	$(MANAGE) seed_finance

.PHONY: users
users: ## Demo foydalanuvchilar (admin, bugalter, sales1, sales2)
	$(MANAGE) seed_users

.PHONY: clients
clients: ## Demo buyurtmachilar (2 jismoniy, 2 yuridik)
	$(MANAGE) seed_clients

.PHONY: demo
demo: seed users clients ## Kassa yacheykalari + demo user + demo buyurtmachi

.PHONY: deadlines
deadlines: ## Muddat eslatmalarini tekshiradi
	$(MANAGE) check_deadlines

.PHONY: static
static: ## Static fayllarni yig'adi
	$(MANAGE) collectstatic --noinput

.PHONY: shell
shell: ## Django shell
	$(MANAGE) shell

.PHONY: setup
setup: install migrate seed ## install + migrate + seed (birinchi ishga tushirish)
	@echo "Tayyor. Endi: make superuser && make run"

# ------------------------------------------------------------------ tekshiruv

.PHONY: test
test: ## Barcha testlarni ishga tushiradi
	$(MANAGE) test apps

.PHONY: check
check: ## Django tekshiruvi + yozilmagan migratsiya bormi
	$(MANAGE) check
	$(MANAGE) makemigrations --check --dry-run

.PHONY: schema
schema: ## OpenAPI schema faylini yig'adi (schema.yml)
	$(MANAGE) spectacular --file schema.yml

.PHONY: ci
ci: check test ## check + test (commitdan oldin)

.PHONY: clean
clean: ## __pycache__ va .pyc fayllarni tozalaydi
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__') if '.venv' not in str(p)]"
	@echo "tozalandi"

# --------------------------------------------------------- docker (server)

.PHONY: build
build: ## Docker image'ni yig'adi
	$(COMPOSE) build

.PHONY: up
up: ## Konteynerni yig'ib ishga tushiradi
	$(COMPOSE) up -d --build

.PHONY: down
down: ## Konteynerni to'xtatadi
	$(COMPOSE) down

.PHONY: restart
restart: ## Konteynerni qayta ishga tushiradi
	$(COMPOSE) restart web

.PHONY: logs
logs: ## Konteyner loglari (jonli)
	$(COMPOSE) logs -f web

.PHONY: ps
ps: ## Konteynerlar holati
	$(COMPOSE) ps

.PHONY: docker-migrate
docker-migrate: ## Konteyner ichida migratsiya
	$(COMPOSE) exec web python manage.py migrate

.PHONY: docker-superuser
docker-superuser: ## Konteyner ichida admin ochish
	$(COMPOSE) exec web python manage.py createsuperuser

.PHONY: docker-users
docker-users: ## Serverda demo foydalanuvchilar
	$(COMPOSE) exec web python manage.py seed_users

.PHONY: docker-clients
docker-clients: ## Serverda demo buyurtmachilar
	$(COMPOSE) exec web python manage.py seed_clients

.PHONY: docker-demo
docker-demo: docker-users docker-clients ## Serverda demo user + buyurtmachi

.PHONY: docker-deadlines
docker-deadlines: ## Konteyner ichida muddat eslatmalari
	$(COMPOSE) exec web python manage.py check_deadlines

.PHONY: docker-dbcheck
docker-dbcheck: ## Konteyner qaysi bazani ishlatayotganini ko'rsatadi
	$(COMPOSE) exec web sh -c 'echo "SQLITE_PATH=$$SQLITE_PATH"; ls -la /app/data'
	$(COMPOSE) exec web python manage.py showmigrations inventory procurement

.PHONY: docker-shell
docker-shell: ## Konteyner ichidagi bash
	$(COMPOSE) exec web bash

.PHONY: deploy
deploy: ## Serverda yangilash: git pull + qayta yig'ish + migratsiya
	git pull
	$(COMPOSE) up -d --build
	$(COMPOSE) exec -T web python manage.py migrate --noinput
	@echo "https://$(DOMAIN)/api/docs/"

.PHONY: backup
backup: ## Bazani zaxiralaydi ($(BACKUP_DIR) ga)
	cp data/db.sqlite3 $(BACKUP_DIR)/ombor-crm-$$(date +%F-%H%M).sqlite3
	@echo "zaxira: $(BACKUP_DIR)"
