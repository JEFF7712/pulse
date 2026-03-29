"""Local HTTP server for Plaid Link (used from `pulse configure` → Connectors → Plaid)."""
from __future__ import annotations

import hashlib
import json
import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pulse.app.config import PulseConfig
from pulse.connectors.plaid_client import make_plaid_client
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

logger = logging.getLogger(__name__)

PLAID_LINK_PORT = 8893


def _stable_client_user_id(token_path: Path) -> str:
    host = socket.gethostname()
    raw = f"{host}:{token_path.parent.resolve()}".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def _link_page_html() -> bytes:
    # Minimal page: fetch link_token, open Plaid Link, POST public_token to server.
    page = """<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>Pulse — Plaid Link</title></head>
<body>
<p>Opening Plaid Link…</p>
<p id="err" style="color:red"></p>
<script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
<script>
async function run() {
  const err = document.getElementById('err');
  try {
    const r = await fetch('/api/create_link_token', { method: 'POST' });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || j.error || 'link_token failed');
    const linkToken = j.link_token;
    const handler = Plaid.create({
      token: linkToken,
      onSuccess: async (public_token, metadata) => {
        const ex = await fetch('/api/exchange', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ public_token }),
        });
        const ej = await ex.json();
        if (!ex.ok) throw new Error(ej.detail || 'exchange failed');
        document.body.innerHTML = '<p>Success. You can close this tab and return to the terminal.</p>';
      },
      onExit: (err, metadata) => {
        if (err != null) err.textContent = err.display_message || 'Link exited';
      },
    });
    handler.open();
  } catch (e) {
    err.textContent = e.message || String(e);
  }
}
run();
</script>
</body></html>"""
    return page.encode("utf-8")


def run_plaid_link_flow(config: PulseConfig, token_path: Path) -> None:
    """Start localhost server, open browser, exchange token, write `token_path`."""
    result: dict[str, Any] = {"done": False, "error": None}
    lock = threading.Lock()

    def fail(msg: str) -> None:
        with lock:
            result["error"] = msg
            result["done"] = True

    def succeed(blob: dict[str, Any]) -> None:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(json.dumps(blob, indent=2))
        with lock:
            result["done"] = True

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            pass

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                html = _link_page_html()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                body = {}

            if path == "/api/create_link_token":
                try:
                    plaid_api, api_client = make_plaid_client(config)
                    try:
                        uid = _stable_client_user_id(token_path)
                        req = LinkTokenCreateRequest(
                            products=[Products("transactions")],
                            client_name="Pulse",
                            country_codes=[CountryCode("US")],
                            language="en",
                            user=LinkTokenCreateRequestUser(client_user_id=uid),
                        )
                        resp = plaid_api.link_token_create(req)
                        d = resp.to_dict()
                        lt = d.get("link_token")
                        if not lt:
                            fail("No link_token in Plaid response")
                            self._send_json(500, {"detail": "no link_token"})
                            return
                        self._send_json(200, {"link_token": lt})
                    finally:
                        api_client.close()
                except Exception as exc:
                    logger.exception("link_token_create")
                    fail(str(exc))
                    self._send_json(500, {"detail": str(exc)})
                return

            if path == "/api/exchange":
                public_token = body.get("public_token")
                if not public_token:
                    self._send_json(400, {"detail": "missing public_token"})
                    return
                try:
                    plaid_api, api_client = make_plaid_client(config)
                    try:
                        ex_req = ItemPublicTokenExchangeRequest(
                            public_token=public_token,
                        )
                        ex_resp = plaid_api.item_public_token_exchange(ex_req)
                        d = ex_resp.to_dict()
                        access = d.get("access_token")
                        item_id = d.get("item_id")
                        if not access:
                            fail("Plaid exchange returned no access_token")
                            self._send_json(500, {"detail": "no access_token"})
                            return
                        succeed(
                            {
                                "access_token": access,
                                "item_id": item_id,
                                "transactions_cursor": None,
                            }
                        )
                        self._send_json(200, {"ok": True})
                    finally:
                        api_client.close()
                except Exception as exc:
                    logger.exception("public_token_exchange")
                    fail(str(exc))
                    self._send_json(500, {"detail": str(exc)})
                return

            self.send_error(404)

    server = HTTPServer(("localhost", PLAID_LINK_PORT), Handler)
    server.timeout = 0.5

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    import webbrowser

    webbrowser.open(f"http://localhost:{PLAID_LINK_PORT}/")

    import time

    deadline = time.time() + 900.0
    while time.time() < deadline:
        with lock:
            if result["done"]:
                break
            err = result["error"]
        if err:
            break
        time.sleep(0.2)
    else:
        fail("Timed out after 15 minutes waiting for Plaid Link.")

    server.shutdown()
    thread.join(timeout=5)

    with lock:
        if result["error"]:
            raise RuntimeError(result["error"])
