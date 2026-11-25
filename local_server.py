"""Serve the local job dashboard on loopback only, without exposing the CV."""
import argparse
import json
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from job_filters import is_senior


def read_jobs(path):
    jobs = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                job = json.loads(line)
                if not is_senior(job):
                    jobs.setdefault(str(job["job_id"]), job)
            except (ValueError, KeyError, TypeError):
                continue
    return list(jobs.values())


def read_analyses(report):
    json_path = report.with_suffix(".json")
    if json_path.exists() and (not report.exists() or json_path.stat().st_mtime >= report.stat().st_mtime):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return {str(row["offre"]["job_id"]): row["analyse"] for row in data["analyses"]}
        except (ValueError, KeyError, TypeError):
            pass
    if not report.exists():
        return {}
    # The running analysis writes its report after each job; JSON appears on completion.
    text = report.read_text(encoding="utf-8")
    analyses = {}
    for block in re.split(r"(?m)^## ", text)[1:]:
        heading = re.match(r"(\d+)/100\s+—[^\n]*\n\s*\[[^\]]*\]\(https://(?:www\.)?seek\.com\.au/job/(\d+)\)\s*\n\s*([^\n]*)", block)
        if not heading:
            continue
        score, job_id, summary = heading.groups()
        def field(label):
            match = re.search(r"(?m)^\*\*" + re.escape(label) + r"\s*:\*\*\s*(.*)$", block)
            return match.group(1) if match else "non précisé"
        analyses[job_id] = {"score": int(score), "resume": summary,
            "points_forts": field("Points forts").split("; "),
            "points_a_verifier": field("À vérifier").split("; "),
            "experience": field("Expérience"), "visa_sponsoring": field("Visa / sponsoring")}
    return analyses


def container_running(container):
    if not container:
        return False
    try:
        result = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", container],
                                capture_output=True, text=True, timeout=3, check=False)
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (OSError, subprocess.TimeoutExpired):
        return False


def state(jobs_path, report, total, container):
    jobs, analyses = read_jobs(jobs_path), read_analyses(report)
    running = container_running(container)
    completed = len(analyses)
    visible_ids = {str(job["job_id"]) for job in jobs}
    analyses = {job_id: analysis for job_id, analysis in analyses.items() if job_id in visible_ids}
    if running:
        status, message = "running", "Analyse locale en cours"
    elif report.with_suffix(".json").exists():
        status, message = "finished", "Analyse terminée ; consulte les résultats"
    else:
        status, message = "stopped", "Analyse non active ou interrompue"
    return {"jobs": jobs, "analyses": analyses,
            "progress": {"completed": completed, "total": total, "status": status, "message": message}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--total", type=int, default=20)
    parser.add_argument("--container", default="")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    html = Path(__file__).parent / "local_ui/index.html"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = urlparse(self.path).path
            if route == "/":
                content, content_type = html.read_bytes(), "text/html; charset=utf-8"
            elif route == "/api/state":
                content = json.dumps(state(args.jobs, args.report, args.total, args.container), ensure_ascii=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

    print(f"SeekSpider : http://127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
