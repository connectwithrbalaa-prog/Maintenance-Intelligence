import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def test_demo_pm_script_exists() -> None:
    script = Path("scripts/demo_pm_approval.sh")
    contents = script.read_text(encoding="utf-8")

    assert script.exists()
    assert contents.startswith("#!/usr/bin/env bash")
    assert "--use-existing-api" in contents
    assert "--run-id" in contents
    assert "pretty_print_json" in contents


def test_demo_pm_script_can_use_existing_api() -> None:
    requests: list[tuple[str, str, str]] = []

    class DemoHandler(BaseHTTPRequestHandler):
        def _write_json(self, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            requests.append(("GET", self.path, ""))
            if self.path == "/healthz":
                self._write_json({"status": "ok"})
                return
            if self.path == "/api/v1/whoami":
                self._write_json(
                    {"org_id": "default-org", "role": "operator", "subject": "planner@example.com"}
                )
                return
            if self.path == "/api/v1/agents/pm/proposals?limit=10":
                self._write_json([{"proposal_id": "demo-proposal", "status": "pending"}])
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            requests.append(("POST", self.path, body))
            if self.path == "/api/v1/agents/pm/advisor/analyze":
                self._write_json({"proposal_id": "demo-proposal"})
                return
            if self.path == "/api/v1/agents/pm/proposals/demo-proposal/approve":
                self._write_json(
                    {
                        "proposal_id": "demo-proposal",
                        "status": "approved",
                        "org_id": "default-org",
                        "proposer_subject": "planner@example.com",
                        "cms_result": {
                            "connector": "mock",
                            "cms_reference": "WO-SMOKE-001",
                            "work_order": {"wo_id": "WO-SMOKE-001", "priority": "high"},
                        },
                    }
                )
                return
            self.send_error(404)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        script = Path("scripts/demo_pm_approval.sh")
        base_url = f"http://127.0.0.1:{server.server_port}"
        run_id = "RUN-DEMO-CLI"
        env = os.environ.copy()
        env["DEMO_PM_START_API"] = "true"

        result = subprocess.run(
            ["bash", str(script), "--use-existing-api", "--api-url", base_url, "--run-id", run_id],
            cwd=Path.cwd(),
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result.returncode == 0, result.stderr
    analyze_body = next(body for method, path, body in requests if method == "POST" and path == "/api/v1/agents/pm/advisor/analyze")
    analyze_payload = json.loads(analyze_body)
    assert analyze_payload["run_id"] == "RUN-DEMO-CLI"
    assert "1) Health check" in result.stdout
    assert "3) Create PM proposal" in result.stdout
    assert '"proposal_id": "demo-proposal"' in result.stdout
    assert "6) Summarize CMMS handoff" in result.stdout
    assert "work_order_id: WO-SMOKE-001" in result.stdout
    assert ("GET", "/healthz", "") in requests
    assert ("GET", "/api/v1/whoami", "") in requests
    assert any(path == "/api/v1/agents/pm/advisor/analyze" for _, path, _ in requests)
    assert any(path == "/api/v1/agents/pm/proposals?limit=10" for _, path, _ in requests)
    assert any(path == "/api/v1/agents/pm/proposals/demo-proposal/approve" for _, path, _ in requests)