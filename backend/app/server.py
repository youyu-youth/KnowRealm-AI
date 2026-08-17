import argparse
from pathlib import Path

import uvicorn

from app.main import create_app


def port_number(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("端口必须在 1 到 65535 之间")
    return port


def main() -> None:
    parser = argparse.ArgumentParser(description="KnowRealm localhost sidecar")
    parser.add_argument("--port", required=True, type=port_number)
    parser.add_argument("--token", required=True)
    parser.add_argument("--data-dir", required=True, type=Path)
    args = parser.parse_args()
    if not args.token:
        parser.error("启动令牌不能为空")

    app = create_app(data_dir=args.data_dir, launch_token=args.token)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
