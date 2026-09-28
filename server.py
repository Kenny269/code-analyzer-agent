#!/usr/bin/env python3
"""Web server for the Code Analyzer Agent."""
import os
import sys
import json
import subprocess
import tempfile
import shutil
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent.orchestrator import Orchestrator
from agent.llm_client import LLMClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_ROOT = os.path.join(BASE_DIR, "skills")
STATIC_DIR = os.path.join(BASE_DIR, "static")


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._serve_file(os.path.join(STATIC_DIR, "index.html"), "text/html")
        elif parsed.path == "/style.css":
            self._serve_file(os.path.join(STATIC_DIR, "style.css"), "text/css")
        elif parsed.path == "/app.js":
            self._serve_file(os.path.join(STATIC_DIR, "app.js"), "application/javascript")
        elif parsed.path == "/api/report":
            self._serve_report(parsed)
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/analyze":
            self._handle_analyze()
        else:
            self._send_json(404, {"error": "not found"})

    # ---- 静态文件 ----

    def _serve_file(self, path, content_type):
        if not os.path.isfile(path):
            self._send_json(404, {"error": "file not found"})
            return
        with open(path, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_report(self, parsed):
        params = parse_qs(parsed.query)
        path = params.get("path", [""])[0]
        if not path or not os.path.isfile(path):
            self._send_json(404, {"error": "report not found"})
            return
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self._send_json(200, {"content": content})

    # ---- 分析接口 ----

    def _handle_analyze(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body)
        except Exception as e:
            self._send_json(400, {"error": f"invalid request: {e}"})
            return

        project_path = payload.get("project_path", "").strip()
        request = payload.get("request", "").strip() or "提取这个系统的业务规则"
        report_dir = payload.get("report_dir", "").strip()

        if not project_path:
            self._send_json(400, {"error": "project path is required"})
            return

        temp_clone_dir = None
        try:
            # Git URL 先克隆
            if project_path.startswith(("http://", "https://", "git@")):
                temp_clone_dir = tempfile.mkdtemp(prefix="code_analyzer_")
                clone_target = os.path.join(temp_clone_dir, "repo")
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", project_path, clone_target],
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode != 0:
                    self._send_json(500, {"error": f"git clone failed: {result.stderr.strip()}"})
                    return
                project_path = clone_target

            if not os.path.isdir(project_path):
                self._send_json(400, {"error": f"path does not exist: {project_path}"})
                return

            # 如果没有 codegraph 索引，自动初始化
            codegraph_dir = os.path.join(project_path, ".codegraph")
            if not os.path.isdir(codegraph_dir):
                init_result = subprocess.run(
                    ["codegraph", "init", "-i"],
                    cwd=project_path, capture_output=True, text=True, timeout=600
                )
                if init_result.returncode != 0:
                    self._send_json(500, {
                        "error": f"codegraph init failed: {init_result.stderr.strip()}"
                    })
                    return

            # 跑 Agent
            llm = None
            try:
                llm = LLMClient()
            except ValueError:
                pass

            orch = Orchestrator(SKILLS_ROOT, llm=llm)
            orch.load_skills()
            result = orch.run(request, project_path)

            # 保存报告
            if not report_dir:
                report_dir = project_path
            if not os.path.isdir(report_dir):
                os.makedirs(report_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = os.path.join(report_dir, f"analysis_report_{timestamp}.json")
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            self._send_json(200, {
                "result": result,
                "report_path": report_file,
            })

        except subprocess.TimeoutExpired:
            self._send_json(500, {"error": "operation timed out"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})
        finally:
            if temp_clone_dir and os.path.isdir(temp_clone_dir):
                shutil.rmtree(temp_clone_dir, ignore_errors=True)

    # ---- 工具方法 ----

    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")


def main():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Server running at http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        server.server_close()


if __name__ == "__main__":
    main()