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


def _set_state(job_id, patch):
    with STATE_LOCK:
        s = STATE.get(job_id) or {}
        s.update(patch)
        STATE[job_id] = s


def _get_state(job_id):
    with STATE_LOCK:
        return dict(STATE.get(job_id) or {})


def _html_page():
    return """<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Verificador de Conflitos de Manobras</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; }
    .field { display: flex; flex-direction: column; gap: 6px; min-width: 220px; }
    label { font-size: 12px; color: #333; }
    input { padding: 8px; font-size: 14px; }
    button { padding: 10px 14px; font-size: 14px; cursor: pointer; }
    .card { border: 1px solid #ddd; padding: 12px; border-radius: 6px; margin-top: 14px; }
    .muted { color: #666; font-size: 12px; }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th, td { border: 1px solid #ddd; padding: 8px; vertical-align: top; }
    th { background: #f6f6f6; text-align: left; }
    .mono { font-family: Consolas, monospace; }
    .bad { color: #a00; }
    .good { color: #060; }
  </style>
</head>
<body>
  <h2>Verificador de Conflitos de Manobras</h2>
  <div class="row">
    <div class="field">
      <label>Manobra base</label>
      <input id="manobra" placeholder="239130082"/>
    </div>
    <div class="field">
      <label>Data início (dd/mm/aaaa)</label>
      <input id="di" placeholder="01/01/2026"/>
    </div>
    <div class="field">
      <label>Data fim (dd/mm/aaaa)</label>
      <input id="df" placeholder="01/01/2026"/>
    </div>
  </div>
  <div class="row" style="margin-top: 10px;">
    <div class="field">
      <label>Usuário</label>
      <input id="user" placeholder="c000000"/>
    </div>
    <div class="field">
      <label>Senha</label>
      <input id="pass" type="password" placeholder=""/>
    </div>
  </div>
  <div class="row" style="margin-top: 12px;">
    <button id="start">Iniciar</button>
    <button id="cancel" disabled>Cancelar</button>
    <a id="export" class="muted" href="#" style="align-self:center; display:none;">Exportar CSV</a>
  </div>

  <div id="status" class="card" style="display:none;">
    <div id="statusText" class="mono"></div>
    <div id="statusSmall" class="muted" style="margin-top:6px;"></div>
  </div>

  <div id="result" class="card" style="display:none;">
    <div id="summary" class="mono"></div>
    <table id="tbl" style="display:none;">
      <thead>
        <tr>
          <th>Manobra</th>
          <th>Equipamentos em comum</th>
          <th>Alimentadores em comum</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

<script>
  let jobId = null;
  let timer = null;

  function qs(id) { return document.getElementById(id); }
  function fmtList(arr) { return (arr && arr.length) ? arr.join("; ") : "-"; }

  function setRunning(r) {
    qs("start").disabled = r;
    qs("cancel").disabled = !r;
  }

  async function start() {
    const payload = new URLSearchParams();
    payload.set("manobra", qs("manobra").value.trim());
    payload.set("di", qs("di").value.trim());
    payload.set("df", qs("df").value.trim());
    payload.set("user", qs("user").value.trim());
    payload.set("pass", qs("pass").value);

    qs("status").style.display = "block";
    qs("result").style.display = "none";
    qs("export").style.display = "none";
    qs("statusText").textContent = "Iniciando...";
    qs("statusSmall").textContent = "";

    const res = await fetch("/start", { method: "POST", body: payload });
    const data = await res.json();
    if (!res.ok) {
      qs("statusText").innerHTML = "<span class='bad'>" + (data.error || "Falha ao iniciar") + "</span>";
      return;
    }
    jobId = data.job_id;
    setRunning(true);
    timer = setInterval(poll, 1000);
    await poll();
  }

  async function cancel() {
    if (!jobId) return;
    await fetch("/cancel?job_id=" + encodeURIComponent(jobId));
  }

  async function poll() {
    if (!jobId) return;
    const res = await fetch("/status?job_id=" + encodeURIComponent(jobId));
    const data = await res.json();
    if (!res.ok) {
      qs("statusText").innerHTML = "<span class='bad'>" + (data.error || "Erro") + "</span>";
      clearInterval(timer);
      setRunning(false);
      return;
    }

    if (data.state === "running") {
      qs("status").style.display = "block";
      qs("statusText").textContent = "PROGRESSO " + data.processed + "/" + data.total + " | conflitos=" + data.conflitos + " | falhas=" + (data.falhas || 0);
      qs("statusSmall").textContent =
        "tempo=" + data.elapsed +
        " | média=" + data.rate_per_min.toFixed(1) + " manobras/min" +
        " | ETA=" + data.eta +
        " | última=" + data.last_seconds.toFixed(2) + "s" +
        " | atual=" + (data.current || "") +
        " | sem update=" + (data.last_update_seconds || 0).toFixed(0) + "s";
      return;
    }

    if (data.state === "error") {
      qs("statusText").innerHTML = "<span class='bad'>" + (data.error || "Erro") + "</span>";
      clearInterval(timer);
      setRunning(false);
      return;
    }

    if (data.state === "done") {
      clearInterval(timer);
      setRunning(false);
      const r = await loadResult();
      if (r) {
        const total = (r.total_unico_sem_base || 0);
        const conflitos = (r.conflitos || []).length;
        const falhas = (r.falhas || []).length;
        qs("statusText").textContent = "FINALIZADO " + total + "/" + total + " | conflitos=" + conflitos + " | falhas=" + falhas + " | tempo=" + (r.elapsed || "-");
        qs("statusSmall").textContent = "";
      }
      return;
    }
  }

  async function loadResult() {
    const res = await fetch("/result?job_id=" + encodeURIComponent(jobId));
    const data = await res.json();
    if (!res.ok) {
      qs("statusText").innerHTML = "<span class='bad'>" + (data.error || "Erro ao carregar resultado") + "</span>";
      return null;
    }
    qs("result").style.display = "block";
    qs("summary").textContent =
      "BASE " + data.base + " | período " + data.data_inicio + " a " + data.data_fim +
      " | EB=" + data.total_eb + " EN=" + data.total_en + " único=" + data.total_unico_sem_base +
      " | conflitos=" + data.conflitos.length + " | falhas=" + (data.falhas ? data.falhas.length : 0) + " | tempo=" + data.elapsed;

    const tbody = qs("tbl").querySelector("tbody");
    tbody.innerHTML = "";
    for (const c of data.conflitos) {
      const tr = document.createElement("tr");
      const td0 = document.createElement("td");
      td0.textContent = c.manobra;
      const td1 = document.createElement("td");
      td1.textContent = fmtList(c.equipamentos);
      const td2 = document.createElement("td");
      td2.textContent = fmtList(c.alimentadores);
      tr.appendChild(td0); tr.appendChild(td1); tr.appendChild(td2);
      tbody.appendChild(tr);
    }
    qs("tbl").style.display = "table";
    qs("export").href = "/export.csv?job_id=" + encodeURIComponent(jobId);
    qs("export").style.display = "inline";
    return data;
  }

  qs("start").addEventListener("click", () => start());
  qs("cancel").addEventListener("click", () => cancel());
</script>
</body>
</html>"""


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


def _run_job(job_id, base, di, df, user, passwd):
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
        r = verificador_conflitos.run_verificacao(base, di, df, user, passwd, progress_cb=cb)
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
        parsed = parse_qs(raw.decode("utf-8", errors="replace"))
        return {k: v[-1] if isinstance(v, list) and v else "" for k, v in parsed.items()}
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


class _Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return _send_text(self, HTTPStatus.OK, _html_page(), "text/html; charset=utf-8")

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
            lines = ["manobra,equipamentos_em_comum,alimentadores_em_comum"]
            for c in r.get("conflitos") or []:
                m = str(c.get("manobra") or "")
                eq = "; ".join(c.get("equipamentos") or [])
                al = "; ".join(c.get("alimentadores") or [])
                lines.append(f"\"{m}\",\"{eq}\",\"{al}\"")
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

        if not base or not di or not df or not user or not passwd:
            return _send_json(self, HTTPStatus.BAD_REQUEST, {"error": "Preencha todos os campos."})

        job_id = str(uuid.uuid4())
        _set_state(job_id, {"state": "queued"})
        t = threading.Thread(target=_run_job, args=(job_id, base, di, df, user, passwd), daemon=True)
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
