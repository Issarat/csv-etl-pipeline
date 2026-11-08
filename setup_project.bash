#!/usr/bin/env bash
set -e

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

[ -f .env ] || cp .env.example .env
[ -x .venv/Scripts/python.exe ] || python -m venv .venv

./.venv/Scripts/python.exe -m pip install -r requirements.txt
docker compose up -d --wait postgres