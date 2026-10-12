# DATABASE_URL and TEST_DATABASE_URL must point at @localhost:5432 when these
# targets run on the Mac. Inside Compose, @db is the database hostname.
# pytest is the api/.venv interpreter so pgvector and the rest of requirements are present.
.PHONY: golden test

golden:
	cd api && .venv/bin/python -m pytest tests/golden -q

test:
	cd api && .venv/bin/python -m pytest -m "not eval" -q
