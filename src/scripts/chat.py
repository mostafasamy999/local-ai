"""Interactive chat in the terminal: model -> JSON -> mock API -> templated answer.

    python scripts/chat.py            # type questions, empty line or Ctrl-D to quit
    python scripts/chat.py --debug    # also print the model JSON and the request filters
    printf 'show my visits today\\nand yesterday?\\n' | python scripts/chat.py --debug   # non-interactive
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import mock_api  # noqa: E402
from app.agent import Agent  # noqa: E402
from app.llm import LLM, load_config  # noqa: E402
from app.responder import respond  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true", help="print the JSON and the request filters")
    ap.add_argument("--adapter", default=None, help="LoRA adapter folder (none = base model)")
    ap.add_argument("--fail-api", action="store_true", help="simulate a backend error")
    args = ap.parse_args()

    config = load_config()
    print("Loading %s ..." % config["model"]["name"], flush=True)
    llm = LLM(config, adapter_path=args.adapter)
    agent = Agent(llm.chat, retries=int(config["agent"]["retries_on_invalid"]))
    interactive = sys.stdin.isatty()
    print("Ready. Ask about your visits and tasks (Arabic or English). Empty line to quit.\n", flush=True)

    while True:
        try:
            text = input("you> ") if interactive else sys.stdin.readline()
        except EOFError:
            break
        if not interactive:
            if not text:
                break
            text = text.rstrip("\n")
            print("you> " + text)
        if not text.strip():
            break

        result = agent.ask(text.strip())
        if args.debug:
            for i, raw in enumerate(result.raw):
                print("  [model%s] %s" % (" retry" if i else "", raw.replace("\n", " ")))
            for e in result.errors:
                print("  [invalid] " + e)
            if result.output:
                print("  [json] " + json.dumps(result.output, ensure_ascii=False))
            if result.request:
                print("  [request] %s %s" % (result.request.endpoint, json.dumps(result.request.filters, ensure_ascii=False)))

        if result.request is None:
            answer = result.text
        else:
            api = mock_api.call(result.request, fail=args.fail_api)
            answer = respond(result.request, api, result.lang)
        print("bot> " + answer + "\n", flush=True)


if __name__ == "__main__":
    main()
