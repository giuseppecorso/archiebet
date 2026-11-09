#!/bin/sh
# Porta il server all'ultima versione di main. Se il backend non diventa sano, termina con errore.
# Le graffe fanno leggere tutto lo script prima di eseguirlo: git può riscrivere questo stesso file.
{
  set -eu
  cd /srv/archie/repo
  git fetch --quiet origin main
  git reset --quiet --hard origin/main
  docker compose -f deploy/compose.yml up -d --build --remove-orphans --wait --wait-timeout 240
  docker image prune -f >/dev/null
  git log -1 --format='Online: %h %s'
  exit 0
}
