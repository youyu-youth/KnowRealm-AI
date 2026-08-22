import argparse
from pathlib import Path

import uvicorn

from app.core.logging import setup_logging
from app.main import create_app


def port_number(value: str) -> int:
    port = int(value)
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("端口必须在 0 到 65535 之间")
    return port


def main() -> None:
    parser = argparse.ArgumentParser(description="KnowRealm localhost sidecar")
    parser.add_argument("--port", required=True, type=port_number)
    parser.add_argument("--token", required=True)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--ffmpeg", required=True, type=Path)
    args = parser.parse_args()
    if not args.token:
        parser.error("启动令牌不能为空")
    if not args.ffmpeg.is_file():
        parser.error("随包 ffmpeg 不存在")

    setup_logging()
    app = create_app(
        data_dir=args.data_dir,
        launch_token=args.token,
        ffmpeg_path=args.ffmpeg,
    )
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_config=None,
        loop="app.core.loop:sidecar_loop_factory",
    )
    server = uvicorn.Server(config)
    listener = config.bind_socket()
    bound_port = listener.getsockname()[1]
    print(f"KNOWREALM_SIDECAR_PORT={bound_port}", flush=True)
    server.run(sockets=[listener])


if __name__ == "__main__":
    main()
