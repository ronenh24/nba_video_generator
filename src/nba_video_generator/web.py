"""Local web interface for running NBA video-generation workflows."""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
import threading
import traceback
import uuid
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from nba_video_generator.nba_agent.config import FFMPEG_PATH


_TEAMS = {
    "atl", "bkn", "bos", "cha", "chi", "cle", "dal", "den", "det", "gsw",
    "hou", "ind", "lac", "lal", "mem", "mia", "mil", "min", "nop", "nyk",
    "okc", "orl", "phi", "phx", "por", "sac", "sas", "tor", "uta", "was",
}
_MAX_REQUEST_BYTES = 64 * 1024
_MAX_LOG_CHARS = 100_000
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_active_job_id: str | None = None


_PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NBA Video Generator</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #080d18; --panel: #111a2b; --panel2: #16223a;
      --line: #293b5a; --muted: #91a0b9; --text: #edf3ff;
      --blue: #438cff; --blue-bright: #6ba7ff; --red: #f05262;
      --green: #64d6a0;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; background: radial-gradient(ellipse at 85% 0%, #182b4b 0, var(--bg) 48%);
      color: var(--text); font: 15px/1.5 Inter, ui-sans-serif, system-ui, sans-serif;
    }
    .shell { width: min(1080px, calc(100% - 40px)); margin: 0 auto; padding: 34px 0 60px; }
    header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 55px; }
    .brand { display: flex; gap: 12px; align-items: center; font-weight: 750; letter-spacing: -.02em; }
    .brand-mark { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 12px;
      background: var(--blue); color: #f7faff; font-size: 17px; font-weight: 900; }
    .local { color: var(--muted); font-size: 12px; border: 1px solid var(--line); border-radius: 99px; padding: 5px 11px; }
    .eyebrow { color: var(--blue-bright); font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .15em; }
    h1 { font-size: clamp(34px, 6vw, 54px); line-height: 1.06; letter-spacing: -.055em; margin: 10px 0 14px; }
    .intro { max-width: 610px; color: var(--muted); margin: 0; }
    .section-head { display: flex; justify-content: space-between; align-items: end; gap: 18px; margin: 38px 0 14px; }
    h2 { font-size: 18px; margin: 0; letter-spacing: -.02em; }
    .section-note { color: var(--muted); font-size: 12px; }
    .layout { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(290px, .8fr); gap: 18px; align-items: start; }
    .card { background: linear-gradient(145deg, #16223a, #101827); border: 1px solid var(--line); border-radius: 16px; padding: 22px; }
    .tabs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 20px; }
    .tab { appearance: none; border: 1px solid var(--line); color: var(--muted); background: #10151d; border-radius: 10px; padding: 11px 8px; font: inherit; font-size: 13px; cursor: pointer; }
    .tab[aria-selected="true"] { background: #172f55; border-color: #3979d4; color: #a9ccff; }
    .form-panel[hidden] { display: none; }
    .field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 13px; }
    label { display: block; color: #c0cad8; font-size: 12px; font-weight: 650; margin-bottom: 6px; }
    input, select { width: 100%; color: var(--text); background: #0d1219; border: 1px solid #303b4b; border-radius: 9px; padding: 10px 11px; font: inherit; outline: none; }
    input:focus, select:focus { border-color: var(--blue); box-shadow: 0 0 0 3px #438cff28; }
    input[type="date"] { color-scheme: dark; }
    .hint { color: var(--muted); font-size: 11px; margin: 6px 0 0; }
    .player-row { display: grid; grid-template-columns: 1.3fr .7fr 1fr 1fr 34px; gap: 8px; align-items: end; margin-bottom: 9px; }
    .player-row label { font-size: 11px; }
    .player-row input { padding: 9px; }
    .remove-row { height: 38px; border: 1px solid var(--line); border-radius: 9px; color: var(--muted); background: #0d1219; cursor: pointer; font-size: 18px; }
    .row-actions { display: flex; justify-content: space-between; align-items: center; margin: 12px 0 18px; }
    .text-button { color: #85b5ff; background: none; border: 0; cursor: pointer; font: inherit; font-size: 12px; padding: 4px 0; }
    .checkbox { display: flex; align-items: center; gap: 9px; margin: 16px 0 2px; color: #c0cad8; font-size: 13px; }
    .checkbox input { width: 15px; height: 15px; accent-color: var(--blue); }
    .button { background: var(--blue); color: #f7faff; border: 0; border-radius: 9px; padding: 11px 17px; font: inherit; font-weight: 800; cursor: pointer; }
    .button:hover:not(:disabled) { background: #2f77e6; }
    .button:disabled { opacity: .5; cursor: wait; }
    .run-row { display: flex; justify-content: space-between; align-items: center; margin-top: 22px; gap: 12px; }
    .status { color: var(--muted); font-size: 12px; }
    .status.running { color: var(--blue-bright); } .status.success { color: var(--green); } .status.error { color: var(--red); }
    .ffmpeg { margin-top: 18px; padding-top: 16px; border-top: 1px solid var(--line); }
    .log-card { min-height: 360px; position: sticky; top: 16px; }
    .log-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
    .live { color: var(--green); font-size: 11px; text-transform: uppercase; letter-spacing: .1em; }
    .live::before { content: ""; display: inline-block; width: 7px; height: 7px; background: var(--green); border-radius: 50%; margin-right: 7px; }
    .log { background: #090c11; border: 1px solid #202a37; border-radius: 10px; color: #b9c5d4; padding: 14px; height: 285px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: 11px/1.6 ui-monospace, SFMono-Regular, Consolas, monospace; }
    .empty { color: #627084; }
    .subtle { color: var(--muted); font-size: 12px; margin: 12px 0 0; }
    @media (max-width: 760px) {
      .shell { width: min(100% - 24px, 560px); padding-top: 22px; }
      header { margin-bottom: 38px; } .layout { grid-template-columns: 1fr; }
      .log-card { position: static; min-height: 0; } .log { height: 220px; }
      .player-row { grid-template-columns: 1fr 1fr; padding: 10px; border: 1px solid var(--line); border-radius: 10px; }
      .player-row .remove-row { grid-column: 2; justify-self: end; width: 34px; }
      .section-head { align-items: start; flex-direction: column; }
    }
    @media (max-width: 420px) { .field-grid { grid-template-columns: 1fr; } .tabs { gap: 5px; } .tab { font-size: 11px; } }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div class="brand"><span class="brand-mark">NBA</span><span>Video Generator</span></div>
      <span class="local">LOCAL WORKSPACE</span>
    </header>
    <div class="eyebrow">Production console</div>
    <h1>Make the plays<br>worth watching.</h1>
    <p class="intro">Run player highlight pipelines, let the daily agent find standout performances, or turn a game's biggest moments into vertical Shorts.</p>

    <div class="section-head">
      <h2>Choose a workflow</h2><span class="section-note">Jobs run on this machine</span>
    </div>
    <div class="layout">
      <section class="card" aria-label="Workflow settings">
        <div class="tabs" role="tablist" aria-label="Workflows">
          <button class="tab" role="tab" aria-selected="true" data-panel="pipeline">Player pipeline</button>
          <button class="tab" role="tab" aria-selected="false" data-panel="agent">Daily agent</button>
          <button class="tab" role="tab" aria-selected="false" data-panel="shorts">Top plays Shorts</button>
        </div>

        <form id="pipeline" class="form-panel">
          <div id="players"></div>
          <div class="row-actions"><button class="text-button" type="button" id="add-player">＋ Add player</button><span class="hint">Up to 20 players</span></div>
          <div class="ffmpeg">
            <label for="pipeline-ffmpeg">FFmpeg executable</label>
            <input id="pipeline-ffmpeg" name="ffmpeg_path" autocomplete="off">
          </div>
          <div class="run-row"><span class="status" id="pipeline-status">Ready to run</span><button class="button" type="submit">Run pipeline&nbsp; →</button></div>
        </form>

        <form id="agent" class="form-panel" hidden>
          <div class="field-grid">
            <div><label for="agent-date">Game date</label><input id="agent-date" name="date" type="date" required></div>
            <div><label>Workflow</label><input value="Find standout performances" disabled></div>
          </div>
          <label class="checkbox"><input type="checkbox" name="threshold" checked> Apply performance thresholds</label>
          <div class="ffmpeg">
            <label for="agent-ffmpeg">FFmpeg executable</label>
            <input id="agent-ffmpeg" name="ffmpeg_path" autocomplete="off">
            <p class="hint">Videos and thumbnails are generated using the agent's configured output folders.</p>
          </div>
          <div class="run-row"><span class="status" id="agent-status">Ready to run</span><button class="button" type="submit">Run daily agent&nbsp; →</button></div>
        </form>

        <form id="shorts" class="form-panel" hidden>
          <div class="field-grid">
            <div><label for="shorts-date">Game date</label><input id="shorts-date" name="date" type="date" required></div>
            <div><label>Format</label><input value="Top plays · vertical 9:16" disabled></div>
          </div>
          <div class="ffmpeg">
            <label for="shorts-ffmpeg">FFmpeg executable</label>
            <input id="shorts-ffmpeg" name="ffmpeg_path" autocomplete="off">
          </div>
          <div class="run-row"><span class="status" id="shorts-status">Ready to run</span><button class="button" type="submit">Make Shorts&nbsp; →</button></div>
        </form>
      </section>

      <aside class="card log-card">
        <div class="log-title"><h2>Run activity</h2><span class="live">Live log</span></div>
        <div class="log" id="log" aria-live="polite"><span class="empty">Your job output will appear here when a workflow starts.</span></div>
        <p class="subtle" id="job-info">The dashboard stays open while work runs in the background.</p>
      </aside>
    </div>
  </main>
  <template id="player-template">
    <div class="player-row">
      <div><label>Player last name</label><input data-field="player" placeholder="Curry" required maxlength="80"></div>
      <div><label>Team</label><input data-field="team" placeholder="gsw" required maxlength="3"></div>
      <div><label>From</label><input data-field="start" type="date" required></div>
      <div><label>To</label><input data-field="end" type="date" required></div>
      <button class="remove-row" type="button" aria-label="Remove player">×</button>
    </div>
  </template>
  <script>
    const defaultFfmpeg = __FFMPEG_JSON__;
    const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    document.querySelectorAll('[name="ffmpeg_path"]').forEach(input => input.value = defaultFfmpeg);
    document.querySelectorAll('[type="date"]').forEach(input => input.value = today);

    const players = document.getElementById('players');
    function addPlayer() {
      if (players.children.length >= 20) return;
      const row = document.getElementById('player-template').content.cloneNode(true);
      row.querySelectorAll('[data-field]').forEach(input => input.name = input.dataset.field);
      row.querySelector('[name="start"]').value = today;
      row.querySelector('[name="end"]').value = today;
      row.querySelector('.remove-row').addEventListener('click', event => {
        if (players.children.length > 1) event.currentTarget.closest('.player-row').remove();
      });
      players.append(row);
    }
    addPlayer();
    document.getElementById('add-player').addEventListener('click', addPlayer);

    document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(other => other.setAttribute('aria-selected', String(other === tab)));
      document.querySelectorAll('.form-panel').forEach(panel => panel.hidden = panel.id !== tab.dataset.panel);
    }));

    let pollTimer;
    const logEl = document.getElementById('log');
    const infoEl = document.getElementById('job-info');
    async function refreshJob(id, form, button, status) {
      try {
        const response = await fetch(`/api/jobs/${id}`);
        if (!response.ok) throw new Error(`Job request failed (${response.status})`);
        const job = await response.json();
        logEl.textContent = job.logs || 'Waiting for output…';
        logEl.scrollTop = logEl.scrollHeight;
        status.className = `status ${job.status}`;
        status.textContent = job.status === 'running' ? 'Running…' : job.status === 'succeeded' ? 'Completed' : job.status === 'failed' ? 'Failed' : job.status;
        infoEl.textContent = `${job.operation_label} · ${job.started_at || 'Starting'}${job.completed_at ? ` · finished ${job.completed_at}` : ''}`;
        if (job.status === 'running') pollTimer = setTimeout(() => refreshJob(id, form, button, status), 900);
        else button.disabled = false;
      } catch (error) {
        status.className = 'status error'; status.textContent = error.message; button.disabled = false;
      }
    }

    const labels = {pipeline: 'Player pipeline', agent: 'Daily agent', shorts: 'Top plays Shorts'};
    document.querySelectorAll('.form-panel').forEach(form => form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = form.querySelector('.button');
      const status = document.getElementById(`${form.id}-status`);
      button.disabled = true;
      status.className = 'status running'; status.textContent = 'Starting…';
      logEl.textContent = 'Submitting job…';
      const ffmpeg_path = form.querySelector('[name="ffmpeg_path"]').value.trim();
      const payload = {operation: form.id, ffmpeg_path};
      if (form.id === 'pipeline') {
        payload.players = [...players.querySelectorAll('.player-row')].map(row => Object.fromEntries(
          [...row.querySelectorAll('[data-field]')].map(input => [input.dataset.field, input.value.trim()])
        ));
      } else {
        payload.date = form.querySelector('[name="date"]').value;
        if (form.id === 'agent') payload.threshold = form.querySelector('[name="threshold"]').checked;
      }
      try {
        const response = await fetch('/api/jobs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
        infoEl.textContent = `${labels[form.id]} · starting`;
        refreshJob(body.id, form, button, status);
      } catch (error) {
        status.className = 'status error'; status.textContent = error.message; button.disabled = false;
        logEl.textContent = error.message;
      }
    }));
  </script>
</body>
</html>
"""


def _valid_date(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a date in YYYY-MM-DD format.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a date in YYYY-MM-DD format.") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} must be a date in YYYY-MM-DD format.")
    return value


def _validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("The request body must be a JSON object.")

    operation = payload.get("operation")
    if operation not in {"pipeline", "agent", "shorts"}:
        raise ValueError("Choose a valid workflow.")

    ffmpeg_path = payload.get("ffmpeg_path", "")
    if not isinstance(ffmpeg_path, str) or len(ffmpeg_path) > 2048:
        raise ValueError("FFmpeg path must be a string of at most 2048 characters.")
    ffmpeg_path = ffmpeg_path.strip() or FFMPEG_PATH

    validated: dict[str, Any] = {
        "operation": operation,
        "ffmpeg_path": ffmpeg_path,
    }
    if operation == "pipeline":
        rows = payload.get("players")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
            raise ValueError("Enter between 1 and 20 player rows.")
        jobs = []
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict):
                raise ValueError(f"Player row {index} is invalid.")
            player = row.get("player")
            team = row.get("team")
            if (not isinstance(player, str)
                    or not re.fullmatch(r"[\w .'-]{1,80}", player.strip())):
                raise ValueError(f"Player row {index}: enter a valid player last name.")
            if not isinstance(team, str) or team.strip().lower() not in _TEAMS:
                raise ValueError(f"Player row {index}: enter a valid NBA team abbreviation.")
            start = _valid_date(row.get("start"), f"Player row {index} start date")
            end = _valid_date(row.get("end"), f"Player row {index} end date")
            if end < start:
                raise ValueError(f"Player row {index}: end date must not be before start date.")
            jobs.append((player.strip(), start, end, team.strip().lower()))
        validated["players"] = jobs
    else:
        validated["date"] = _valid_date(payload.get("date"), "Game date")
        if operation == "agent":
            threshold = payload.get("threshold", True)
            if not isinstance(threshold, bool):
                raise ValueError("Performance thresholds must be enabled or disabled.")
            validated["threshold"] = threshold
    return validated


class _JobLogWriter:
    encoding = "utf-8"

    def __init__(self, job_id: str, mirror: Any):
        self.job_id = job_id
        self.mirror = mirror

    def write(self, text: str) -> int:
        with _jobs_lock:
            job = _jobs.get(self.job_id)
            if job is not None:
                job["logs"] = (job["logs"] + text)[-_MAX_LOG_CHARS:]
        self.mirror.write(text)
        self.mirror.flush()
        return len(text)

    def flush(self) -> None:
        self.mirror.flush()

    def isatty(self) -> bool:
        return False


def _run_job(job_id: str, payload: dict[str, Any]) -> None:
    global _active_job_id
    writer = _JobLogWriter(job_id, _ORIGINAL_STDOUT)
    try:
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            operation = payload["operation"]
            if operation == "pipeline":
                from nba_video_generator.src.beta_search import pipeline

                result = pipeline(
                    payload["players"],
                    {"ffmpeg_path": payload["ffmpeg_path"]},
                )
            elif operation == "agent":
                from nba_video_generator.nba_agent import run_agent

                result = run_agent(
                    payload["date"],
                    payload["ffmpeg_path"],
                    threshold=payload["threshold"],
                    approve=False,
                )
            else:
                from nba_video_generator.nba_shorts import make_shorts_for_date

                result = make_shorts_for_date(
                    payload["date"],
                    payload["ffmpeg_path"],
                )
            print(f"\nWorkflow completed. Result: {result!r}")
        status = "succeeded"
    except Exception as exc:
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            traceback.print_exc()
        with _jobs_lock:
            _jobs[job_id]["error"] = str(exc)
        status = "failed"
    finally:
        with _jobs_lock:
            job = _jobs[job_id]
            job["status"] = status
            job["completed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            _active_job_id = None


_ORIGINAL_STDOUT = sys.stdout


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _Handler(BaseHTTPRequestHandler):
    server_version = "NBAVideoGenerator/1.0"

    def log_message(self, _format: str, *args: Any) -> None:
        return

    def _send_json(self, status: int, data: dict[str, Any]) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            page = _PAGE.replace("__FFMPEG_JSON__", json.dumps(FFMPEG_PATH))
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        match = re.fullmatch(r"/api/jobs/([0-9a-f-]{36})", path)
        if match:
            with _jobs_lock:
                job = _jobs.get(match.group(1))
                if job is None:
                    self._send_json(404, {"error": "Job not found."})
                    return
                self._send_json(200, dict(job))
            return

        self._send_json(404, {"error": "Not found."})

    def do_POST(self) -> None:
        global _active_job_id
        if urlparse(self.path).path != "/api/jobs":
            self._send_json(404, {"error": "Not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= _MAX_REQUEST_BYTES:
                raise ValueError("Request size must be between 1 byte and 64 KB.")
            payload = _validate_payload(json.loads(self.rfile.read(length)))
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": str(exc)})
            return

        job_id = str(uuid.uuid4())
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        operation_labels = {
            "pipeline": "Player pipeline",
            "agent": "Daily agent",
            "shorts": "Top plays Shorts",
        }
        job = {
            "id": job_id,
            "operation": payload["operation"],
            "operation_label": operation_labels[payload["operation"]],
            "status": "running",
            "started_at": now,
            "completed_at": None,
            "logs": "",
            "error": None,
        }
        with _jobs_lock:
            if _active_job_id is not None:
                self._send_json(409, {"error": "Another workflow is already running. Wait for it to finish before starting another."})
                return
            _active_job_id = job_id
            _jobs[job_id] = job

        thread = threading.Thread(
            target=_run_job,
            args=(job_id, payload),
            name=f"nba-video-job-{job_id[:8]}",
            daemon=True,
        )
        thread.start()
        self._send_json(202, {"id": job_id})


def main() -> None:
    parser = argparse.ArgumentParser(description="Open the NBA Video Generator web dashboard.")
    parser.add_argument("--port", type=int, default=8765, help="Local web server port (default: 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser automatically")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    address = ("127.0.0.1", args.port)
    try:
        server = _Server(address, _Handler)
    except OSError as exc:
        parser.error(f"Could not start local server at http://127.0.0.1:{args.port}: {exc}")
    url = f"http://127.0.0.1:{args.port}"
    print(f"NBA Video Generator is available at {url} (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping NBA Video Generator.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
