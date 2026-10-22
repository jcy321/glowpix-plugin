#!/usr/bin/env python3
import base64
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "z-image-spicy"
API_KEY = os.environ.get("SMOKE_API_KEY", "smoke-key")
PORT = int(os.environ.get("SMOKE_PORT", "8092"))

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

LOCK = threading.Lock()
REQUESTS = []
TASKS = {}
COUNTER = {"n": 0}
CONFIG = {"queries_until_terminal": 2, "terminal_status": "SUCCESS"}


def now():
    return int(time.time())


def reset():
    with LOCK:
        REQUESTS.clear()
        TASKS.clear()
        COUNTER["n"] = 0
        CONFIG["queries_until_terminal"] = 2
        CONFIG["terminal_status"] = "SUCCESS"


def record(method, path, headers, body):
    with LOCK:
        REQUESTS.append(
            {
                "method": method,
                "path": path,
                "authorization": headers.get("Authorization", ""),
                "content_type": headers.get("Content-Type", ""),
                "body": body,
                "at": now(),
            }
        )


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("[smoke] " + (fmt % args), flush=True)

    def send_json(self, status, payload):
        data = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return "__invalid__"

    def authorized(self):
        return self.headers.get("Authorization", "") == "Bearer " + API_KEY

    def unauthorized(self):
        self.send_json(401, {"code": "invalid_api_key", "data": None, "message": "invalid api key"})

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return
        if path == "/_smoke/requests":
            with LOCK:
                self.send_json(200, {"requests": list(REQUESTS)})
            return
        if path == "/_smoke/image.png":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(PNG)))
            self.end_headers()
            self.wfile.write(PNG)
            return

        prefix = "/v1/inference/" + MODEL + "/"
        if path.startswith(prefix):
            record("GET", path, self.headers, None)
            if not self.authorized():
                self.unauthorized()
                return
            task_id = path[len(prefix):]
            with LOCK:
                task = TASKS.get(task_id)
                if task is None:
                    self.send_json(
                        400,
                        {"code": "task_not_exist", "data": None, "message": "task_not_exist"},
                    )
                    return
                task["polls"] += 1
                polls = task["polls"]
                terminal_after = CONFIG["queries_until_terminal"]
                terminal_status = CONFIG["terminal_status"]

            if polls <= terminal_after:
                pending = polls == 1
                payload = {
                    "code": "success",
                    "data": {
                        "action": "generate",
                        "created_at": task["created_at"],
                        "data": {
                            "task_info": {
                                "created_at": task["iso"],
                                "id": task["uuid"],
                                "status": "pending" if pending else "processing",
                                "updated_at": task["iso"],
                            }
                        },
                        "fail_reason": "",
                        "finish_time": 0,
                        "id": task["n"],
                        "platform": "Resource Endpoint",
                        "progress": "0%" if pending else "30%",
                        "properties": {"input": "", "origin_model_name": MODEL},
                        "quota": 7150,
                        "result_url": "http://127.0.0.1:%d/v1/videos/%s/content" % (PORT, task_id),
                        "start_time": task["created_at"],
                        "status": "NOT_START" if pending else "IN_PROGRESS",
                        "submit_time": task["created_at"],
                        "task_id": task_id,
                        "updated_at": now(),
                    },
                    "message": "",
                }
                self.send_json(200, payload)
                return

            image_url = "http://127.0.0.1:%d/_smoke/image.png" % PORT
            if terminal_status == "FAILURE":
                payload = {
                    "code": "success",
                    "data": {
                        "action": "generate",
                        "created_at": task["created_at"],
                        "data": {
                            "task_info": {
                                "created_at": task["iso"],
                                "id": task["uuid"],
                                "status": "failed",
                                "updated_at": task["iso"],
                            }
                        },
                        "fail_reason": "smoke failure",
                        "finish_time": now(),
                        "id": task["n"],
                        "platform": "Resource Endpoint",
                        "progress": "100%",
                        "properties": {"input": "", "origin_model_name": MODEL},
                        "quota": 7150,
                        "result_url": "",
                        "start_time": task["created_at"],
                        "status": "FAILURE",
                        "submit_time": task["created_at"],
                        "task_id": task_id,
                        "updated_at": now(),
                    },
                    "message": "",
                }
                self.send_json(200, payload)
                return

            payload = {
                "code": "success",
                "data": {
                    "action": "generate",
                    "created_at": task["created_at"],
                    "data": {
                        "images": [image_url],
                        "task_info": {
                            "created_at": task["iso"],
                            "id": task["uuid"],
                            "status": "completed",
                            "updated_at": task["iso"],
                        },
                    },
                    "fail_reason": "",
                    "finish_time": now(),
                    "id": task["n"],
                    "platform": "Resource Endpoint",
                    "progress": "100%",
                    "properties": {"input": "", "origin_model_name": MODEL},
                    "quota": 7150,
                    "result_url": image_url,
                    "start_time": task["created_at"],
                    "status": "SUCCESS",
                    "submit_time": task["created_at"],
                    "task_id": task_id,
                    "updated_at": now(),
                },
                "message": "",
            }
            self.send_json(200, payload)
            return

        self.send_json(404, {"code": "not_found", "data": None, "message": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        body = self.read_json()

        if path == "/_smoke/reset":
            reset()
            self.send_json(200, {"status": "reset"})
            return
        if path == "/_smoke/config":
            if not isinstance(body, dict):
                self.send_json(400, {"code": "invalid_request", "data": None, "message": "config must be an object"})
                return
            with LOCK:
                if "queries_until_terminal" in body:
                    value = body["queries_until_terminal"]
                    if not isinstance(value, int) or value < 0 or value > 10:
                        self.send_json(400, {"code": "invalid_request", "data": None, "message": "queries_until_terminal must be 0..10"})
                        return
                    CONFIG["queries_until_terminal"] = value
                if "terminal_status" in body:
                    value = body["terminal_status"]
                    if value not in ("SUCCESS", "FAILURE"):
                        self.send_json(400, {"code": "invalid_request", "data": None, "message": "terminal_status must be SUCCESS or FAILURE"})
                        return
                    CONFIG["terminal_status"] = value
            self.send_json(200, {"status": "ok", "config": dict(CONFIG)})
            return

        if path == "/v1/inference/" + MODEL:
            record("POST", path, self.headers, body)
            if not self.authorized():
                self.unauthorized()
                return
            if body == "__invalid__" or not isinstance(body, dict):
                self.send_json(400, {"code": "invalid_request", "data": None, "message": "invalid JSON body"})
                return
            allowed = {"prompt", "size"}
            unknown = sorted(set(body) - allowed)
            if unknown:
                self.send_json(
                    400,
                    {
                        "code": "invalid_request",
                        "data": None,
                        "message": "unexpected field: " + unknown[0],
                    },
                )
                return
            prompt = body.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                self.send_json(400, {"code": "invalid_request", "data": None, "message": "prompt is required"})
                return
            size = body.get("size")
            if size is not None:
                if not isinstance(size, str):
                    self.send_json(400, {"code": "invalid_request", "data": None, "message": "size must be a string"})
                    return
                parts = size.lower().split("x")
                if len(parts) != 2 or not all(p.isdigit() and int(p) > 0 for p in parts):
                    self.send_json(400, {"code": "invalid_request", "data": None, "message": "size must be WIDTHxHEIGHT"})
                    return

            with LOCK:
                COUNTER["n"] += 1
                n = COUNTER["n"]
                task_id = "task_smoke_%d" % n
                TASKS[task_id] = {
                    "n": n,
                    "uuid": "00000000-0000-4000-8000-%012d" % n,
                    "created_at": now(),
                    "iso": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                    "polls": 0,
                }
            self.send_json(
                200,
                {
                    "created_at": now(),
                    "id": task_id,
                    "model": MODEL,
                    "object": "video",
                    "progress": 0,
                    "status": "queued",
                    "task_id": task_id,
                },
            )
            return

        self.send_json(404, {"code": "not_found", "data": None, "message": "not found"})


if __name__ == "__main__":
    reset()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("[smoke] listening on :%d" % PORT, flush=True)
    server.serve_forever()
