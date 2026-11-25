import json
import threading
from datetime import UTC, date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from github_trending_wechat.delivery import DeliveryService, ServerChanProvider
from github_trending_wechat.pipeline import DigestApplication
from github_trending_wechat.sources import (
    GitHubRepositoryEnricher,
    GitHubTrendingSource,
    SourceError,
    SourceOrchestrator,
)
from github_trending_wechat.storage import DeliveryStore, DigestStore
from github_trending_wechat.summarizer import ChineseSummarizer

NOW = datetime(2026, 11, 25, 8, 0, tzinfo=UTC)


class FailIfCalled:
    def fetch(self, now: datetime):
        raise SourceError("fallback should not be called")


class StubHandler(BaseHTTPRequestHandler):
    pushes: list[dict[str, list[str]]] = []

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/trending":
            articles = []
            for index in range(1, 11):
                articles.append(
                    f"""<article class="Box-row">
                    <h2><a href="/owner/repo-{index}">owner/repo-{index}</a></h2>
                    <p class="col-9">Description {index}</p>
                    <span itemprop="programmingLanguage">Python</span>
                    <a href="/owner/repo-{index}/stargazers">{1000 + index}</a>
                    <span class="float-sm-right">{100 + index} stars today</span>
                    </article>"""
                )
            self._reply(200, "<html><body>" + "".join(articles) + "</body></html>", "text/html")
            return
        if self.path.startswith("/repos/owner/repo-"):
            index = int(self.path.rsplit("-", 1)[1])
            self._reply(
                200,
                json.dumps(
                    {
                        "description": f"Repository {index} description",
                        "language": "Python",
                        "stargazers_count": 2000 + index,
                    }
                ),
                "application/json",
            )
            return
        self._reply(404, "not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/SCT_TEST.send":
            length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(length).decode()
            self.__class__.pushes.append(parse_qs(body))
            self._reply(
                200,
                json.dumps({"code": 0, "data": {"pushid": "stub-message"}}),
                "application/json",
            )
            return
        self._reply(404, "not found", "text/plain")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _reply(self, status: int, body: str, content_type: str) -> None:
        encoded = body.encode()
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def test_end_to_end_local_http_stub_and_idempotent_second_run(tmp_path: Path) -> None:
    StubHandler.pushes = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        client = httpx.Client(timeout=2)
        digest_store = DigestStore(tmp_path)
        delivery_store = DeliveryStore(tmp_path)
        application = DigestApplication(
            sources=SourceOrchestrator(
                GitHubTrendingSource(client, f"{base}/trending"),
                FailIfCalled(),
                GitHubRepositoryEnricher(client, api_base=base),
            ),
            summarizer=ChineseSummarizer(client),
            digest_store=digest_store,
            delivery_service=DeliveryService(
                ServerChanProvider(client, "SCT_TEST", api_base=base),
                delivery_store,
                now=lambda: NOW,
            ),
            now=lambda: NOW,
        )

        application.now = lambda: datetime(2026, 11, 24, 15, 55, tzinfo=UTC)
        application.capture(scheduled=True)
        application.now = lambda: NOW
        first = application.run(date(2026, 11, 24))
        second = application.run(date(2026, 11, 24))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    stored = digest_store.load(date(2026, 11, 24))
    attempts = delivery_store.load(date(2026, 11, 24))
    assert stored is not None and len(stored.entries) == 10
    assert first.attempt is not None and first.attempt.status == "success"
    assert second.attempt is not None and second.attempt.status == "idempotent_skip"
    assert [attempt.status for attempt in attempts] == ["success", "idempotent_skip"]
    assert len(StubHandler.pushes) == 1
    assert "owner/repo-1" in StubHandler.pushes[0]["desp"][0]
