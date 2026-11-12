#!/bin/bash
# Usage: ./scripts/train.sh v1
set -e

VERSION=$1
if [ -z "$VERSION" ]; then
  echo "Usage: ./scripts/train.sh <version>   (e.g. v1)"
  exit 1
fi

cd "$(dirname "$0")/.."
source .venv/bin/activate

mlx_lm.lora \
  --model mlx-community/Qwen2.5-3B-Instruct-4bit \
  --train \
  --data "./dataset/$VERSION" \
  --iters 600 \
  --batch-size 1 \
  --num-layers 4 \
  --grad-checkpoint \
  --adapter-path "./adapters/$VERSION"

echo "Training done for $VERSION. Adapter saved at ./adapters/$VERSION"
