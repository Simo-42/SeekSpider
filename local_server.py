"""Serve the local job dashboard on loopback only, without exposing the CV."""
import argparse
import json
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from job_filters import experience_exclusion, is_senior


def read_jobs(path, include_senior=False):
    jobs = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                job = json.loads(line)
                if include_senior or not is_senior(job):
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


def state(jobs_path, report, total, container, profile=None):
    all_jobs = read_jobs(jobs_path, include_senior=True)
    analyses = read_analyses(report)
    running = container_running(container)
    excluded_ids = {job_id for job_id, analysis in analyses.items()
                    if experience_exclusion(analysis.get("preuve_experience", ""))}
    failures = 0
    try:
        saved = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
        failures = len(saved.get("echecs", []))
        excluded_ids.update(str(row["job"]["job_id"]) for row in saved.get("exclusions", []))
    except (OSError, ValueError, TypeError, KeyError):
        pass
    jobs = [job for job in all_jobs if not is_senior(job) and str(job["job_id"]) not in excluded_ids]
    visible_ids = {str(job["job_id"]) for job in jobs}
    analyses = {job_id: analysis for job_id, analysis in analyses.items() if job_id in visible_ids}
    completed = len(analyses)
    if running:
        status, message = "running", "Analyse locale en cours"
    elif all_jobs and completed == len(jobs) and not failures:
        status, message = "finished", "Analyse terminée ; consulte les résultats"
    else:
        status = "stopped"
        message = (f"Analyse en pause : {failures} offre(s) à réessayer" if failures
                   else "Analyse en pause ; les résultats enregistrés sont conservés")
    return {"jobs": jobs, "analyses": analyses,
            "progress": {"completed": completed, "total": len(jobs), "status": status, "message": message,
                         "excluded": len(all_jobs) - len(jobs),
                         "failed": failures,
                         "can_start": bool(profile and profile.is_file() and jobs and not running and completed < len(jobs)),
                         "can_stop": running}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--total", type=int, default=20)
    parser.add_argument("--container", default="")
    parser.add_argument("--profile", type=Path, help="Profil ou CV texte local pour l'analyse")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    html = Path(__file__).parent / "local_ui/index.html"
    container = "seekspider-ranking"
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = urlparse(self.path).path
            if route == "/":
                content, content_type = html.read_bytes(), "text/html; charset=utf-8"
            elif route == "/api/state":
                content = json.dumps(state(args.jobs, args.report, args.total, container, args.profile), ensure_ascii=False).encode("utf-8")
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

        def do_POST(self):
            origin = self.headers.get("Origin", "")
            allowed = {f"http://localhost:{args.port}", f"http://127.0.0.1:{args.port}"}
            if origin not in allowed or self.headers.get_content_type() != "application/json":
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 4096 or length < 0:
                    raise ValueError("Requête trop volumineuse")
                self.rfile.read(length)
                route = urlparse(self.path).path
                with lock:
                    if route == "/api/analysis/start":
                        current = state(args.jobs, args.report, args.total, container, args.profile)
                        if not current["progress"]["can_start"]:
                            raise ValueError("Démarrage impossible : profil manquant, aucune offre restante ou analyse déjà active.")
                        project = Path(__file__).resolve().parent
                        command = ["docker", "run", "-d", "--rm", "--name", container,
                            "--network", "container:seekspider-ollama", "--entrypoint", "python",
                            "-v", f"{project}:/src:ro", "-v", f"{args.jobs.resolve()}:/data/jobs.jsonl:ro",
                            "-v", f"{args.report.resolve().parent}:/results",
                            "-v", f"{args.profile.resolve()}:/private/profile.txt:ro", "seekspider-run",
                            "/src/local_rank.py", "/data/jobs.jsonl", f"/results/{args.report.name}",
                            "--profile", "/private/profile.txt", "--limit", "1000000", "--resume"]
                        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                        if result.returncode:
                            raise ValueError("Impossible de lancer l'analyse. Vérifie que Docker, Ollama et l'image seekspider-run sont démarrés.")
                    elif route == "/api/analysis/stop":
                        if not container_running(container):
                            raise ValueError("Aucune analyse active.")
                        result = subprocess.run(["docker", "stop", "-t", "15", container], capture_output=True, text=True, timeout=25)
                        if result.returncode:
                            raise ValueError("Impossible d'arrêter l'analyse.")
                    else:
                        self.send_error(404)
                        return
                payload, code = {"ok": True}, 200
            except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
                payload, code = {"error": str(exc)}, 400
            content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    print(f"SeekSpider : http://127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
