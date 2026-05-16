from __future__ import annotations

import argparse
import json

from app.services import model_gateway


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Spark model gateway configuration and optional live call.")
    parser.add_argument("--call", action="store_true", help="Run a real Spark WebSocket call when credentials are present.")
    parser.add_argument("--prompt", default="请用一句话说明栈为什么适合做括号匹配。")
    args = parser.parse_args()

    status = model_gateway.get_model_status()
    payload: dict = {"status": status}
    if args.call:
        if status["mode"] != "spark":
            payload["result"] = "Spark credentials or websocket dependency are not ready; no live call was made."
        else:
            payload["result"] = model_gateway.generate_text(args.prompt, fallback="")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
