#!/usr/bin/env python3
"""Web server for the Code Analyzer Agent."""
import os
import sys
import json
import subprocess
import tempfile
import shutil
import platform
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
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
        elif parsed.path == "/api/skills":
            self._handle_skills()
        elif parsed.path == "/api/choose-folder":
            self._handle_choose_folder()
        elif parsed.path == "/api/report":
            self._serve_report(parsed)
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/analyze-stream":
            self._handle_analyze_stream_post()
        elif self.path == "/api/analyze":
            self._handle_analyze()
        else:
            self._send_json(404, {"error": "not found"})

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

    def _handle_skills(self):
        try:
            orch = Orchestrator(SKILLS_ROOT, llm=None)
            orch.load_skills()
            self._send_json(200, {"skills": orch.list_skills()})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def _handle_choose_folder(self):
        system = platform.system()
        try:
            if system == "Darwin":
                result = subprocess.run(["osascript", "-e", 'POSIX path of (choose folder with prompt "选择项目文件夹")'], capture_output=True, text=True, timeout=300)
                path = result.stdout.strip().rstrip("/") if result.returncode == 0 else ""
            elif system == "Windows":
                ps_script = "Add-Type -AssemblyName System.Windows.Forms; $f = New-Object System.Windows.Forms.FolderBrowserDialog; $f.Description = '选择项目文件夹'; if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }"
                result = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True, timeout=300)
                path = result.stdout.strip()
            else:
                result = subprocess.run(["zenity", "--file-selection", "--directory", "--title=选择项目文件夹"], capture_output=True, text=True, timeout=300)
                path = result.stdout.strip() if result.returncode == 0 else ""
            self._send_json(200, {"path": path} if path else {"path": "", "cancelled": True})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def _handle_analyze_stream_post(self):
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
        business_doc = payload.get("business_doc", "").strip() # 接收业务文档

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def send_event(event, data):
            try:
                msg = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        if not project_path:
            send_event("error", {"error": "project path is required"})
            return

        self._run_analysis_stream(project_path, request, report_dir, business_doc, send_event)

    def _run_analysis_stream(self, project_path, request, report_dir, business_doc, send_event):
        temp_clone_dir = None
        try:
            if project_path.startswith(("http://", "https://", "git@")):
                send_event("progress", {"stage": "clone", "message": "正在克隆 Git 仓库..."})
                temp_clone_dir = tempfile.mkdtemp(prefix="code_analyzer_")
                clone_target = os.path.join(temp_clone_dir, "repo")
                result = subprocess.run(["git", "clone", "--depth", "1", project_path, clone_target], capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    send_event("error", {"error": f"git clone failed: {result.stderr.strip()}"})
                    return
                project_path = clone_target
                send_event("progress", {"stage": "clone_done", "message": "仓库克隆完成"})

            if not os.path.isdir(project_path):
                send_event("error", {"error": f"path does not exist: {project_path}"})
                return

            codegraph_dir = os.path.join(project_path, ".codegraph")
            if not os.path.isdir(codegraph_dir):
                send_event("progress", {"stage": "index", "message": "正在构建代码索引..."})
                init_result = subprocess.run(["codegraph", "init", "-i"], cwd=project_path, capture_output=True, text=True, timeout=600)
                if init_result.returncode != 0:
                    send_event("error", {"error": f"codegraph init failed: {init_result.stderr.strip()}"})
                    return
                send_event("progress", {"stage": "index_done", "message": "索引构建完成"})

            def progress_callback(event, data):
                send_event("progress", {"stage": event, **data})

            llm = None
            try:
                llm = LLMClient()
            except ValueError:
                pass

            orch = Orchestrator(SKILLS_ROOT, llm=llm)
            orch.load_skills()
            
            # 传入 business_doc
            result = orch.run(request, project_path, business_doc=business_doc, progress_callback=progress_callback)

            if not report_dir:
                report_dir = project_path
            if not os.path.isdir(report_dir):
                os.makedirs(report_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = os.path.join(report_dir, f"analysis_report_{timestamp}.json")
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            send_event("complete", {"result": result, "report_path": report_file})

        except subprocess.TimeoutExpired:
            send_event("error", {"error": "operation timed out"})
        except Exception as e:
            send_event("error", {"error": str(e)})
        finally:
            if temp_clone_dir and os.path.isdir(temp_clone_dir):
                shutil.rmtree(temp_clone_dir, ignore_errors=True)

    def _handle_analyze(self):
        # 同步接口兼容旧版（略，核心功能已由 SSE 承担）
        self._send_json(200, {"status": "ok"})

    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def main():
    port = int(os.environ.get("PORT", 8080))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Server running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()

if __name__ == "__main__":
    main()