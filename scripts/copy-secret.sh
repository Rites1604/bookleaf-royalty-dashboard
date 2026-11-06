#!/bin/sh
# Copies one n8n credential value to the clipboard without printing it.
# Usage: scripts/copy-secret.sh webhook|anthropic
FILE="$(dirname "$0")/../n8n-credentials-to-paste.txt"
case "$1" in
  webhook) n=1 ;;
  anthropic) n=2 ;;
  *) echo "usage: $0 webhook|anthropic" >&2; exit 1 ;;
esac
awk -v n="$n" '/^ *Value:/ { if (++i == n) { sub(/^ *Value: */, ""); printf "%s", $0 } }' "$FILE" | pbcopy
echo "Copied the $1 value to the clipboard ($(pbpaste | wc -c | tr -d ' ') characters)."
