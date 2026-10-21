#!/bin/sh
# Migrazioni, poi (solo in modalità demo) utente demo + storico gratuito + previsioni, infine il server.
set -e
alembic upgrade head
if [ "${DEMO:-0}" = "1" ]; then
  python -m app.cli demo-setup
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
