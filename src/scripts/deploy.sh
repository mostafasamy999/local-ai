#!/bin/bash
# Usage: ./scripts/deploy.sh v2
#
# NOTE: we deliberately do NOT run mlx_lm.fuse anymore. Fusing a LoRA
# adapter into a 4-bit quantized base model forces a dequantize ->
# merge -> re-quantize round trip, and that re-quantization step was
# observed to flip borderline predictions (confirmed by comparing
# mlx_lm.generate with --adapter-path directly vs the fused model).
# Serving with --adapter-path avoids that precision loss entirely, at
# the cost of a small per-request LoRA compute overhead (negligible
# for a 3B model on M1 Pro).
set -e

VERSION=$1
if [ -z "$VERSION" ]; then
  echo "Usage: ./scripts/deploy.sh <version>   (e.g. v2)"
  exit 1
fi

cd "$(dirname "$0")/.."

if [ ! -d "./adapters/$VERSION" ]; then
  echo "Error: ./adapters/$VERSION does not exist. Train it first: ./scripts/train.sh $VERSION"
  exit 1
fi

rm -f ./adapters/current
ln -s "./$VERSION" ./adapters/current

echo "Deployed $VERSION -> adapters/current now points to adapters/$VERSION"
echo "Restart the server now:"
echo "  mlx_lm.server --model mlx-community/Qwen2.5-3B-Instruct-4bit --adapter-path ./adapters/current --host 0.0.0.0 --port 8080"
