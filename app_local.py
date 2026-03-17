import json
import os
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

import verificador_conflitos


STATE_LOCK = threading.Lock()
STATE = {}


def _app_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _set_state(job_id, patch):
    with STATE_LOCK:
        s = STATE.get(job_id) or {}
        s.update(patch)
        STATE[job_id] = s


def _get_state(job_id):
    with STATE_LOCK:
        return dict(STATE.get(job_id) or {})


def _html_page():
    html_path = os.path.join(_app_dir(), "temp", "index.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "<!doctype html><html><head><meta charset='utf-8'/><title>Erro</title></head><body>Falha ao carregar temp/index.html</body></html>"


def _fmt_seconds(seconds):
    try:
        s = int(round(float(seconds)))
    except:
        s = 0
    if s < 0:
        s = 0
    h = s // 3600
    m = (s % 3600) // 60
    ss = s % 60
    if h:
        return f"{h:02d}:{m:02d}:{ss:02d}"
    return f"{m:02d}:{ss:02d}"


def _parse_situacoes_param(raw):
    s = (raw or "").strip()
    if not s:
        return []
    parts = []
    cur = ""
    for ch in s:
        if ch in {",", ";", " "}:
            if cur:
                parts.append(cur)
                cur = ""
            continue
        cur += ch
    if cur:
        parts.append(cur)
    out = []
    seen = set()
    for p in parts:
        v = (p or "").strip().upper()
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def _parse_malhas_param(raw):
    # Reutiliza a mesma lógica de _parse_situacoes_param
    return _parse_situacoes_param(raw)


def _run_job(job_id, base, di, df, user, passwd, situacoes, malhas):
    _set_state(
        job_id,
        {
            "state": "running",
            "processed": 0,
            "total": 0,
            "elapsed": "00:00",
            "eta": "00:00",
            "rate_per_min": 0.0,
            "last_seconds": 0.0,
            "conflitos": 0,
            "falhas": 0,
            "current": "",
            "cancel": False,
            "last_update_at": time.time(),
        },
    )

    started_at = time.perf_counter()

    def cb(p):
        st = _get_state(job_id)
        if st.get("cancel"):
            raise RuntimeError("Cancelado pelo usuário.")
        elapsed = p.get("elapsed_seconds", 0.0)
        eta = p.get("eta_seconds", 0.0)
        _set_state(
            job_id,
            {
                "state": "running",
                "processed": int(p.get("processed") or 0),
                "total": int(p.get("total") or 0),
                "elapsed": _fmt_seconds(elapsed),
                "eta": _fmt_seconds(eta),
                "rate_per_min": float(p.get("rate_per_min") or 0.0),
                "last_seconds": float(p.get("last_seconds") or 0.0),
                "conflitos": int(p.get("conflitos") or 0),
                "falhas": int(p.get("falhas") or 0),
                "current": str(p.get("current") or ""),
                "last_update_at": time.time(),
            },
        )

    try:
        r = verificador_conflitos.run_verificacao(base, di, df, user, passwd, progress_cb=cb, situacoes=situacoes, malhas=malhas)
        elapsed_total = time.perf_counter() - started_at
        _set_state(
            job_id,
            {
                "state": "done",
                "result": {
                    **r,
                    "elapsed": _fmt_seconds(elapsed_total),
                },
            },
        )
    except Exception as e:
        _set_state(job_id, {"state": "error", "error": str(e)})


def _parse_body(handler):
    length = int(handler.headers.get("Content-Length") or "0")
    raw = handler.rfile.read(length) if length > 0 else b""
    ct = handler.headers.get("Content-Type") or ""
    if "application/x-www-form-urlencoded" in ct:
        # Modificado para lidar com múltiplos valores (para checkboxes)
        parsed = parse_qs(raw.decode("utf-8", errors="replace"))
        out = {}
        for k, v in parsed.items():
            if isinstance(v, list):
                # Junta múltiplos valores com vírgula, ex: malhas=CN&malhas=LE -> "CN,LE"
                out[k] = ",".join(v)
            else:
                out[k] = v
        return out
    try:
        return json.loads(raw.decode("utf-8", errors="replace") or "{}")
    except:
        return {}


def _send_json(handler, code, obj):
    payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _send_text(handler, code, text, content_type):
    payload = (text or "").encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _send_bytes(handler, code, payload, content_type):
    data = payload if isinstance(payload, (bytes, bytearray)) else (payload or b"")
    handler.send_response(code)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _read_asset_bytes(filename):
    safe = os.path.basename(filename or "")
    allowed = {"icon_light.ico", "icon_light.png"}
    if safe not in allowed:
        return None, None
    path = os.path.join(_app_dir(), "assents", safe)
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        return None, None
    if safe.lower().endswith(".ico"):
        return data, "image/x-icon"
    if safe.lower().endswith(".png"):
        return data, "image/png"
    return None, None


class _Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return _send_text(self, HTTPStatus.OK, _html_page(), "text/html; charset=utf-8")

        if u.path == "/favicon.ico":
            data, content_type = _read_asset_bytes("icon_light.ico")
            if data:
                return _send_bytes(self, HTTPStatus.OK, data, content_type)
            return _send_text(self, HTTPStatus.NOT_FOUND, "Not Found", "text/plain; charset=utf-8")

        if u.path.startswith("/assents/"):
            name = (u.path.split("/")[-1] or "").strip()
            data, content_type = _read_asset_bytes(name)
            if data:
                return _send_bytes(self, HTTPStatus.OK, data, content_type)
            return _send_text(self, HTTPStatus.NOT_FOUND, "Not Found", "text/plain; charset=utf-8")

        if u.path == "/status":
            q = parse_qs(u.query)
            job_id = (q.get("job_id") or [""])[-1]
            st = _get_state(job_id)
            if not st:
                return _send_json(self, HTTPStatus.NOT_FOUND, {"error": "Job não encontrado"})
            if st.get("state") == "running":
                last_update_at = float(st.get("last_update_at") or time.time())
                last_update_seconds = max(0.0, time.time() - last_update_at)
                return _send_json(
                    self,
                    HTTPStatus.OK,
                    {
                        "state": "running",
                        "processed": st.get("processed", 0),
                        "total": st.get("total", 0),
                        "elapsed": st.get("elapsed", "00:00"),
                        "eta": st.get("eta", "00:00"),
                        "rate_per_min": st.get("rate_per_min", 0.0),
                        "last_seconds": st.get("last_seconds", 0.0),
                        "conflitos": st.get("conflitos", 0),
                        "falhas": st.get("falhas", 0),
                        "current": st.get("current", ""),
                        "last_update_seconds": last_update_seconds,
                    },
                )
            if st.get("state") == "done":
                return _send_json(self, HTTPStatus.OK, {"state": "done"})
            if st.get("state") == "error":
                return _send_json(self, HTTPStatus.OK, {"state": "error", "error": st.get("error", "Erro")})
            return _send_json(self, HTTPStatus.OK, {"state": st.get("state", "unknown")})

        if u.path == "/result":
            q = parse_qs(u.query)
            job_id = (q.get("job_id") or [""])[-1]
            st = _get_state(job_id)
            if not st or st.get("state") != "done":
                return _send_json(self, HTTPStatus.NOT_FOUND, {"error": "Resultado não disponível"})
            return _send_json(self, HTTPStatus.OK, st.get("result") or {})

        if u.path == "/export.csv":
            q = parse_qs(u.query)
            job_id = (q.get("job_id") or [""])[-1]
            st = _get_state(job_id)
            if not st or st.get("state") != "done":
                return _send_text(self, HTTPStatus.NOT_FOUND, "Resultado não disponível", "text/plain; charset=utf-8")
            r = st.get("result") or {}
            lines = ["manobra,situacoes,equipamentos_em_comum,alimentadores_em_comum"]
            for c in r.get("conflitos") or []:
                m = str(c.get("manobra") or "")
                si = "; ".join(c.get("situacoes") or [])
                eq = "; ".join(c.get("equipamentos") or [])
                al = "; ".join(c.get("alimentadores") or [])
                lines.append(f"\"{m}\",\"{si}\",\"{eq}\",\"{al}\"")
            return _send_text(self, HTTPStatus.OK, "\n".join(lines) + "\n", "text/csv; charset=utf-8")

        if u.path == "/cancel":
            q = parse_qs(u.query)
            job_id = (q.get("job_id") or [""])[-1]
            st = _get_state(job_id)
            if not st:
                return _send_json(self, HTTPStatus.NOT_FOUND, {"error": "Job não encontrado"})
            _set_state(job_id, {"cancel": True})
            return _send_json(self, HTTPStatus.OK, {"ok": True})

        return _send_text(self, HTTPStatus.NOT_FOUND, "Not Found", "text/plain; charset=utf-8")

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/start":
            return _send_text(self, HTTPStatus.NOT_FOUND, "Not Found", "text/plain; charset=utf-8")

        body = _parse_body(self)
        base = (body.get("manobra") or "").strip()
        di = (body.get("di") or "").strip()
        df = (body.get("df") or "").strip()
        user = (body.get("user") or "").strip()
        passwd = body.get("pass") or ""
        situacoes = _parse_situacoes_param(body.get("situacoes") or "")
        malhas = _parse_malhas_param(body.get("malhas") or "")

        if not base or not di or not df or not user or not passwd:
            return _send_json(self, HTTPStatus.BAD_REQUEST, {"error": "Preencha todos os campos."})

        if not situacoes:
            return _send_json(self, HTTPStatus.BAD_REQUEST, {"error": "Selecione ao menos 1 situação."})
        
        # Se nenhuma malha for selecionada, default para buscar em todas
        if not malhas:
            malhas = [""]

        job_id = str(uuid.uuid4())
        _set_state(job_id, {"state": "queued"})
        t = threading.Thread(target=_run_job, args=(job_id, base, di, df, user, passwd, situacoes, malhas), daemon=True)
        t.start()
        return _send_json(self, HTTPStatus.OK, {"job_id": job_id})

    def log_message(self, fmt, *args):
        return


def main():
    host = "127.0.0.1"
    port = int((os.getenv("GDIS_PORT") or "8765").strip())
    httpd = _Server((host, port), Handler)
    print(f"Servidor local: http://{host}:{port}/")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
