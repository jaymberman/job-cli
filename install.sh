#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALIASES_FILE="$HOME/.bash_aliases"
ALIAS_LINE="alias job='python3 $REPO_DIR/job.py'"

touch "$ALIASES_FILE"

if grep -q "^alias job=" "$ALIASES_FILE"; then
    sed -i.bak "s|^alias job=.*|$ALIAS_LINE|" "$ALIASES_FILE"
    rm -f "$ALIASES_FILE.bak"
    echo "Updated existing 'job' alias in $ALIASES_FILE"
else
    echo "$ALIAS_LINE" >> "$ALIASES_FILE"
    echo "Added 'job' alias to $ALIASES_FILE"
fi

echo "Run 'source ~/.bash_aliases' (or open a new shell) to start using: job"
