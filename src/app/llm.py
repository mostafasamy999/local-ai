"""Load the Qwen model with mlx_lm and turn (system prompt + messages) into text.

The model is read from the local Hugging Face cache only (HF_HUB_OFFLINE=1). Nothing is downloaded.
"""
import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from pathlib import Path  # noqa: E402
from typing import Dict, List, Optional  # noqa: E402

import yaml  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "model_config.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_system_prompt(config: Optional[dict] = None) -> str:
    config = config or load_config()
    with open(ROOT / config["model"]["system_prompt_file"], encoding="utf-8") as f:
        return f.read().strip()


class LLM:
    def __init__(self, config: Optional[dict] = None, adapter_path: Optional[str] = None) -> None:
        from mlx_lm import load
        from mlx_lm.sample_utils import make_sampler

        self.config = config or load_config()
        m = self.config["model"]
        adapter = adapter_path or m.get("adapter_path")
        if adapter:
            adapter = str((ROOT / adapter).resolve()) if not os.path.isabs(adapter) else adapter
        self.model, self.tokenizer = load(m["name"], adapter_path=adapter)
        self.max_tokens = int(m.get("max_tokens", 256))
        self.sampler = make_sampler(temp=float(m.get("temperature", 0.0)))
        self.system_prompt = load_system_prompt(self.config)

    def build_prompt(self, messages: List[Dict[str, str]]) -> str:
        full = [{"role": "system", "content": self.system_prompt}] + list(messages)
        return self.tokenizer.apply_chat_template(full, add_generation_prompt=True, tokenize=False)

    def chat(self, messages: List[Dict[str, str]]) -> str:
        """messages = user/assistant turns only (no system). Returns the raw model text."""
        from mlx_lm import generate

        prompt = self.build_prompt(messages)
        return generate(self.model, self.tokenizer, prompt=prompt, max_tokens=self.max_tokens,
                        sampler=self.sampler, verbose=False).strip()
