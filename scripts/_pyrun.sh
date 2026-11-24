#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Tries python3 → python → py -3 on PATH; on Windows, falls back to common
# Python install locations because Git Bash launched by some hooks gets a
# stripped PATH that omits the Windows Python directory.
# Designed to be sourced or called as: bash scripts/_pyrun.sh <script> [args...]
#
# Exits 0 silently if no Python is found — hooks must never block the AI tool.
set -u

PY=""

if command -v py >/dev/null 2>&1; then
  PY="py -3"
else
  # Prefer real Windows Python interpreters for hooks so they share the same
  # packages and .env behavior as the normal PowerShell workflow.
  shopt -s nullglob 2>/dev/null || true
  for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe \
    /mnt/c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/mnt/c/Program Files/Python"*/python.exe \
    "/mnt/c/Program Files (x86)/Python"*/python.exe \
    /mnt/c/Python*/python.exe; do
    if [ -x "$cand" ]; then PY="$cand"; break; fi
  done
  shopt -u nullglob 2>/dev/null || true
fi

if [ -z "$PY" ] && command -v python3 >/dev/null 2>&1; then
  PY=python3
elif [ -z "$PY" ] && command -v python >/dev/null 2>&1; then
  PY=python
fi

[ -n "$PY" ] || exit 0

# shellcheck disable=SC2086
exec $PY "$@"
