#!/usr/bin/env bash
# Find or clone the open-subsurface-data repository and check that the osd tool runs.
# Usage: bash setup.sh [repository folder]
# Set OSD_REPO_URL to clone from somewhere other than the default.
set -euo pipefail

REPO_URL="${OSD_REPO_URL:-https://github.com/mnky9800n/open-subsurface-data}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for tool in uv curl git; do
  command -v "$tool" >/dev/null || { echo "missing: $tool"; exit 1; }
done

# 1. an explicit folder, 2. the checkout this skill sits in, 3. ~/open-subsurface-data, 4. clone
if [ $# -ge 1 ]; then
  repo="$1"
elif [ -f "$here/../../../pyproject.toml" ] && grep -q 'name = "open-subsurface-data"' "$here/../../../pyproject.toml"; then
  repo="$(cd "$here/../../.." && pwd)"
else
  repo="$HOME/open-subsurface-data"
fi

if [ ! -f "$repo/pyproject.toml" ]; then
  git clone --depth 1 "$REPO_URL" "$repo"
fi

cd "$repo"
uv run osd --version
echo "repository: $repo"
echo "run commands from there: cd $repo && uv run osd sources"
