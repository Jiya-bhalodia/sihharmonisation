import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def test_cors_header_is_kept_on_unhandled_server_errors():
    api = FastAPI()

    @api.get("/login-failure")
    def login_failure():
        raise RuntimeError("simulated unexpected error")

    origin = "https://bhumi-x.netlify.app"
    app = CORSMiddleware(
        app=api,
        allow_origins=[origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/login-failure",
        "raw_path": b"/login-failure",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"api.example.test"), (b"origin", origin.encode())],
        "client": ("127.0.0.1", 1234),
        "server": ("api.example.test", 443),
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    try:
        asyncio.run(app(scope, receive, send))
    except RuntimeError as error:
        assert str(error) == "simulated unexpected error"

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    response_headers = dict(response_start["headers"])
    assert response_start["status"] == 500
    assert response_headers[b"access-control-allow-origin"] == origin.encode()
