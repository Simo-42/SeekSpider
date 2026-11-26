"""Serve the local job dashboard on loopback only, without exposing the CV."""
import argparse
import json
import math
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from cv_profile import profile_fingerprint, profile_summary
from job_filters import (DEFAULT_MODEL, SCORE_VERSION, experience_evidence, experience_exclusion,
                         is_senior, is_target_role, role_category, whv_flags)

TRIAGE_STATUSES = ("todo", "shortlist", "applied", "dismissed")


def triage_path(report: Path) -> Path:
    return report.with_name(report.stem + ".triage.json")


def read_triage(report: Path) -> dict:
    path = triage_path(report)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    triage = {}
    for job_id, entry in raw.items():
        if not isinstance(job_id, str) or not job_id.strip() or not isinstance(entry, dict):
            continue
        status = entry.get("status")
        note = entry.get("note", "")
        updated_at = entry.get("updated_at")
        if (status in TRIAGE_STATUSES and isinstance(note, str) and len(note) <= 500
                and isinstance(updated_at, (int, float)) and not isinstance(updated_at, bool)
                and math.isfinite(updated_at)):
            triage[job_id] = {"status": status, "note": note, "updated_at": updated_at}
    return triage


def save_triage_entry(report: Path, job_id: str, status: str, note: str = "") -> dict | None:
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("Identifiant d'offre invalide.")
    if not isinstance(status, str) or status not in TRIAGE_STATUSES:
        raise ValueError("Statut de triage invalide.")
    if not isinstance(note, str):
        raise ValueError("La note doit être un texte.")
    job_id = job_id.strip()
    note = note.strip()
    if len(note) > 500:
        raise ValueError("La note ne peut pas dépasser 500 caractères.")
    data = read_triage(report)
    if status == "todo" and note == "":
        data.pop(job_id, None)
        entry = None
    else:
        entry = {"status": status, "note": note, "updated_at": round(time.time(), 3)}
        data[job_id] = entry
    path = triage_path(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return entry


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
    if json_path.exists():
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


def read_search(jobs_path):
    try:
        saved = json.loads(jobs_path.resolve().with_suffix(".search.json").read_text(encoding="utf-8"))
        return saved if isinstance(saved, dict) else {}
    except (OSError, ValueError):
        return {}


def search_state(jobs_path, running, analysing):
    saved = read_search(jobs_path)
    try:
        status = saved["status"]
        completed, total, new_jobs = (int(saved[key]) for key in ("completed", "total", "new_jobs"))
    except (OSError, ValueError, KeyError, TypeError):
        saved = {}
        status, completed, total, new_jobs = "idle", 0, 0, 0
    if running:
        status = "running"
    elif status == "running":
        status = "failed"
    if status == "running":
        message = "Recherche SEEK en cours."
    elif status == "finished":
        message = f"Recherche terminée. Nouvelles annonces SEEK collectées : {new_jobs}."
    elif status == "failed":
        message = "Recherche interrompue ou incomplète. Les offres enregistrées restent disponibles."
    else:
        status, message = "idle", ""
    elapsed_seconds = remaining_seconds = None
    started, updated = saved.get("started_at"), saved.get("updated_at")
    if all(isinstance(value, (int, float)) and math.isfinite(value) for value in (started, updated)) and updated >= started:
        active = running and saved.get("status") == "running"
        elapsed = max(0, (time.time() if active else updated) - started)
        elapsed_seconds = int(elapsed)
        if active and 4 <= completed < total:
            # Use completed pages only to estimate the rate, and allow time already spent on the next page.
            projection = (updated - started) * total / completed - elapsed
            if projection > 0:
                remaining_seconds = math.ceil(projection)
    return {"status": status, "message": message, "completed": completed, "total": total,
            "new_jobs": new_jobs, "can_start": not running and not analysing,
            "elapsed_seconds": elapsed_seconds, "remaining_seconds": remaining_seconds,
            "discovered_jobs": saved.get("discovered_jobs"), "last_query": saved.get("last_query", ""),
            "recent_new_jobs": saved.get("recent_new_jobs", [])}


def state(jobs_path, report, total, container, profile=None, search_container=""):
    try:
        profile_text = profile.read_text(encoding="utf-8") if profile else ""
    except (OSError, UnicodeError):
        profile_text = ""
    fingerprint = profile_fingerprint(profile_text)
    all_jobs = read_jobs(jobs_path, include_senior=True)
    analyses = read_analyses(report)
    for job_id, analysis in list(analyses.items()):
        updated = dict(analysis)
        saved_fingerprint = updated.pop("profile_fingerprint", None)
        updated["score_obsolete"] = updated.get("score_method") != SCORE_VERSION or saved_fingerprint != fingerprint
        if updated["score_obsolete"]:
            updated["score"] = None
        updated.setdefault("habilitation", "Aucune mention repérée automatiquement : vérifie l'annonce.")
        updated.setdefault("preuve_habilitation", "Aucun extrait pertinent repéré automatiquement")
        old_experience = updated.get("preuve_experience", "")
        if old_experience and not experience_evidence(old_experience):
            updated["preuve_experience"] = "Aucun extrait pertinent repéré automatiquement"
            updated["experience"] = "Expérience demandée à vérifier dans l'annonce."
        old_visa = updated.get("preuve_visa", "")
        if (re.search(r"\b(?:regardless\s+of|without\s+regard\s+to)\b[^.]{0,200}\bcitizenship\b", old_visa, re.I)
                and not re.search(r"\b(?:visa|sponsor\w*|work(?:ing)?\s+rights?|right\s+to\s+work)\b", old_visa, re.I)):
            updated["preuve_visa"] = "Aucun extrait pertinent repéré automatiquement"
            updated["visa_sponsoring"] = "Visa et droit au travail à vérifier dans l'annonce."
        updated["whv_flags"] = whv_flags(updated)
        analyses[job_id] = updated
    running = container_running(container)
    searching = container_running(search_container)
    excluded_ids = {job_id for job_id, analysis in analyses.items()
                    if experience_exclusion(analysis.get("preuve_experience", ""))}
    failed_ids = set()
    try:
        saved = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
        failed_ids = {str(row["job"]["job_id"]) for row in saved.get("echecs", [])}
        excluded_ids.update(str(row["job"]["job_id"]) for row in saved.get("exclusions", []))
    except (OSError, ValueError, TypeError, KeyError):
        pass
    jobs = [job for job in all_jobs if not is_senior(job) and is_target_role(job)
            and str(job["job_id"]) not in excluded_ids]
    for job in jobs:
        job["role_category"] = role_category(job)
    visible_ids = {str(job["job_id"]) for job in jobs}
    analyses = {job_id: analysis for job_id, analysis in analyses.items() if job_id in visible_ids}
    current_ids = {job_id for job_id, analysis in analyses.items() if not analysis["score_obsolete"]}
    failures = len((failed_ids & visible_ids) - current_ids)
    completed = len(current_ids)
    stale = len(analyses) - completed
    pending = len(jobs) - completed
    if running:
        status, message = "running", "Analyse locale en cours"
    elif all_jobs and completed == len(jobs) and not failures:
        status, message = "finished", "Analyse terminée ; consulte les résultats"
    else:
        status = "stopped"
        message = (f"Analyse en pause : {stale} score(s) à recalculer, {pending - stale} offre(s) à analyser, {failures} échec(s) à réessayer" if pending or failures
                   else "Analyse en pause ; les résultats enregistrés sont conservés")
    triage = {job_id: entry for job_id, entry in read_triage(report).items() if job_id in visible_ids}
    return {"jobs": jobs, "analyses": analyses, "triage": triage, "profile": profile_summary(profile_text),
            "search": search_state(jobs_path, searching, running),
            "progress": {"completed": completed, "total": len(jobs), "status": status, "message": message,
                         "model": DEFAULT_MODEL,
                         "excluded": len(all_jobs) - len(jobs),
                         "stale": stale,
                         "pending": pending,
                         "failed": failures,
                         "can_start": bool(profile_text.strip() and jobs and not running and not searching and completed < len(jobs)),
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
    search_container = "seekspider-search"
    project = Path(__file__).resolve().parent
    jobs_path = args.jobs.resolve()
    lock = threading.Lock()

    handoff = {"pending": False, "message": ""}

    def current_state():
        return state(args.jobs, args.report, args.total, container, args.profile, search_container)

    def start_analysis(collected=None):
        network = ["--network", "container:seekspider-ollama"] if container_running("seekspider-ollama") else []
        extra_mount = ["-v", f"{collected}:/private/collected.json:ro"] if collected else []
        subset = ["--collected", "/private/collected.json"] if collected else []
        command = ["docker", "run", "-d", "--rm", "--name", container,
            *network, "--entrypoint", "python",
            "-v", f"{project}:/src:ro", "-v", f"{jobs_path}:/data/jobs.jsonl:ro",
            "-v", f"{args.report.resolve().parent}:/results",
            "-v", f"{args.profile.resolve()}:/private/profile.txt:ro", *extra_mount, "seekspider-run",
            "/src/local_rank.py", "/data/jobs.jsonl", f"/results/{args.report.name}",
            "--profile", "/private/profile.txt", "--model", DEFAULT_MODEL, "--limit", "1000000", "--resume", *subset]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError("Impossible de lancer l'analyse. Vérifie Docker et la présence de l'image seekspider-run.")

    def analyse_after_search(worker_id):
        message = ""
        try:
            result = subprocess.run(["docker", "wait", worker_id], capture_output=True, text=True, timeout=420)
            if result.returncode or result.stdout.strip() != "0":
                return
            with lock:
                saved = read_search(jobs_path)
                added = set(saved.get("added_job_ids", []))
                if saved.get("status") != "finished" or not added:
                    return
                current = current_state()
                if not any(str(job["job_id"]) in added for job in current["jobs"]):
                    message = "Aucune nouvelle offre dans les familles ciblées."
                elif not current["progress"]["can_start"]:
                    message = "Analyse automatique en attente. Vérifiez le CV chargé ou utilisez « Démarrer ou reprendre »."
                else:
                    start_analysis(jobs_path.with_suffix(".search.json"))
                    message = "Analyse automatique des nouvelles offres lancée."
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"Analyse après collecte : {exc}", flush=True)
            message = "Analyse automatique indisponible. Utilisez « Démarrer ou reprendre »."
        finally:
            with lock:
                handoff.update(pending=False, message=message)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = urlparse(self.path).path
            if route == "/":
                content, content_type = html.read_bytes(), "text/html; charset=utf-8"
            elif route == "/api/state":
                payload = current_state()
                with lock:
                    pending, handoff_message = handoff["pending"], handoff["message"]
                if pending:
                    payload["search"]["can_start"] = payload["progress"]["can_start"] = False
                if payload["search"]["status"] == "finished":
                    message = "Démarrage de l’analyse des nouvelles offres…" if pending else handoff_message
                    if message:
                        payload["search"]["message"] += " " + message
                content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
                body = self.rfile.read(length)
                route = urlparse(self.path).path
                payload, code = {"ok": True}, 200
                with lock:
                    if route == "/api/search/start":
                        if handoff["pending"] or container_running(container) or container_running(search_container):
                            raise ValueError("Une recherche ou une analyse est déjà en cours.")
                        jobs_path.parent.mkdir(parents=True, exist_ok=True)
                        command = ["docker", "run", "-d", "--rm", "--name", search_container,
                            "--entrypoint", "python", "-v", f"{project}:/src:ro", "-v", f"{jobs_path.parent}:/jobs",
                            "seekspider-run", "/src/targeted_search.py", f"/jobs/{jobs_path.name}", "--merge"]
                        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                        if result.returncode:
                            raise ValueError("Impossible de lancer la recherche. Vérifie Docker et l’image seekspider-run.")
                        handoff.update(pending=True, message="")
                        threading.Thread(target=analyse_after_search, args=(result.stdout.strip(),), daemon=True).start()
                    elif route == "/api/analysis/start":
                        if handoff["pending"] or not current_state()["progress"]["can_start"]:
                            raise ValueError("Démarrage impossible : profil manquant, aucune offre restante ou une tâche est déjà active.")
                        start_analysis()
                    elif route == "/api/analysis/stop":
                        if not container_running(container):
                            raise ValueError("Aucune analyse active.")
                        result = subprocess.run(["docker", "stop", "-t", "15", container], capture_output=True, text=True, timeout=25)
                        if result.returncode:
                            raise ValueError("Impossible d'arrêter l'analyse.")
                    elif route == "/api/triage":
                        try:
                            data = json.loads(body.decode("utf-8")) if body else None
                        except (UnicodeDecodeError, ValueError) as exc:
                            raise ValueError("Corps JSON invalide.") from exc
                        if not isinstance(data, dict):
                            raise ValueError("Corps JSON invalide.")
                        entry = save_triage_entry(
                            args.report,
                            data.get("job_id"),
                            data.get("status"),
                            data.get("note", ""),
                        )
                        payload = {"ok": True, "triage": entry}
                    else:
                        self.send_error(404)
                        return
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
