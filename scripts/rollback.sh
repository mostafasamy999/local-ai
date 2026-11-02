#!/bin/bash
# Usage: ./scripts/rollback.sh v1
set -e

VERSION=$1
if [ -z "$VERSION" ]; then
  echo "Usage: ./scripts/rollback.sh <version>   (e.g. v1)"
  exit 1
fi

cd "$(dirname "$0")/.."

if [ ! -d "./adapters/$VERSION" ]; then
  echo "Error: no adapter named $VERSION in adapters/"
  exit 1
fi

rm -f ./adapters/current
ln -s "./$VERSION" ./adapters/current

echo "Rolled back -> adapters/current now points to adapters/$VERSION"
echo "Restart the server now:"
echo "  mlx_lm.server --model mlx-community/Qwen2.5-3B-Instruct-4bit --adapter-path ./adapters/current --host 0.0.0.0 --port 8080"
