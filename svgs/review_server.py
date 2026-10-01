from __future__ import annotations

import json
import os
import tempfile
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent
PNG_ROOT = ROOT.parent / "pngs" / "originals"
REVIEWS_PATH = ROOT / "reviews.json"
HOST = "127.0.0.1"
PORT = 8765


def valid_reviews(payload: Any) -> bool:
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return False
    reviews = payload.get("reviews")
    if not isinstance(reviews, dict):
        return False

    allowed_statuses = {"pending", "approved", "changes-requested"}
    for file_name, review in reviews.items():
        if not isinstance(file_name, str) or not file_name.endswith(".svg"):
            return False
        if not isinstance(review, dict):
            return False
        if review.get("status") not in allowed_statuses:
            return False
        if not isinstance(review.get("remark", ""), str):
            return False
    return True


def write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    handle, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


class ReviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:
        if self.path == "/api/reviews":
            self.send_json_file(REVIEWS_PATH)
            return
        if urlsplit(self.path).path.startswith("/pngs/"):
            self.send_png()
            return
        super().do_GET()

    def do_PUT(self) -> None:
        if self.path != "/api/reviews":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 2_000_000:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(content_length))
            if not valid_reviews(payload):
                raise ValueError("Invalid reviews JSON")
            write_json_atomically(REVIEWS_PATH, payload)
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error(HTTPStatus.BAD_REQUEST, str(error))
            return

        response = json.dumps({"saved": True}).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def send_json_file(self, path: Path) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def send_png(self) -> None:
        requested_name = Path(unquote(urlsplit(self.path).path)).name
        path = (PNG_ROOT / requested_name).resolve()
        if path.parent != PNG_ROOT.resolve() or path.suffix.lower() != ".png":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, message: str, *args: Any) -> None:
        print(f"[review] {self.address_string()} - {message % args}")


def main() -> None:
    url = f"http://{HOST}:{PORT}/"
    server = ThreadingHTTPServer((HOST, PORT), ReviewHandler)
    print(f"AIRKAN SVG review server: {url}")
    print(f"Reviews are saved to: {REVIEWS_PATH}")
    print("Press Ctrl+C to stop.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping review server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
