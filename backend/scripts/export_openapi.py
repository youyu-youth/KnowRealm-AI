import argparse
import json
from pathlib import Path

from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI contract")
    parser.add_argument("output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    schema = create_app(data_dir=Path("."), launch_token="schema-export").openapi()
    rendered = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(
                "OpenAPI schema 已漂移，请运行 pnpm --filter @knowrealm/api-types generate"
            )
        return

    args.output.write_text(rendered, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
