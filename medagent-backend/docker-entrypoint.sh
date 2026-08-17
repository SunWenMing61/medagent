#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python -m alembic -x database=postgres upgrade head
  python -m alembic -x database=mysql upgrade head
fi

exec "$@"
