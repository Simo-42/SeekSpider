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
from job_filters import (DEFAULT_MODEL, SCORE_VERSION, contract_duration, employer_tag,
                         experience_evidence, experience_exclusion, is_senior, is_target_role,
                         normalized_dedup_key, recruiter_contacts, role_category, whv_flags,
                         work_mode)

TRIAGE_STATUSES = ("todo", "shortlist", "applied", "dismissed")
MAX_TRIAGE_ENTRIES = 5000
MAX_JOB_ID_LENGTH = 128
AI_UNAVAILABLE_MODEL = "Notes IA indisponibles"
DOCKER_HARDENING = ("--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=256")
STALE_LOCATION_LEAK = re.compile(r"\b(?:bois[- ]colombes|paris|relocation)\b", re.I)
CONTAINER_CACHE_TTL = 2.0

_FILE_CACHE = {}
_FILE_CACHE_LOCK = threading.Lock()
_CONTAINER_CACHE = {}
_CONTAINER_CACHE_LOCK = threading.Lock()


def _cached_read(path, loader, default=None):
    if not path:
        return default
    key = (loader.__name__, str(path.resolve()))
    try:
        st = path.stat()
    except OSError:
        with _FILE_CACHE_LOCK:
            _FILE_CACHE.pop(key, None)
        return default
    stamp = (st.st_mtime_ns, st.st_size, st.st_ino)
    with _FILE_CACHE_LOCK:
        cached = _FILE_CACHE.get(key)
        if cached and cached[0] == stamp:
            return cached[1]
    try:
        value = loader(path)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        return default
    with _FILE_CACHE_LOCK:
        if len(_FILE_CACHE) > 128:
            _FILE_CACHE.clear()
        _FILE_CACHE[key] = (stamp, value)
    return value


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def triage_path(report: Path) -> Path:
    return report.with_name(report.stem + ".triage.json")


def _load_triage(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    triage = {}
    for job_id, entry in raw.items():
        if (not isinstance(job_id, str) or not job_id.strip() or len(job_id.strip()) > MAX_JOB_ID_LENGTH
                or not isinstance(entry, dict)):
            continue
        status = entry.get("status")
        note = entry.get("note", "")
        updated_at = entry.get("updated_at")
        if (status in TRIAGE_STATUSES and isinstance(note, str) and len(note) <= 500
                and isinstance(updated_at, (int, float)) and not isinstance(updated_at, bool)
                and math.isfinite(updated_at)):
            triage[job_id] = {"status": status, "note": note, "updated_at": updated_at}
    return triage


def read_triage(report: Path) -> dict:
    cached = _cached_read(triage_path(report), _load_triage, default={})
    return {job_id: dict(entry) for job_id, entry in cached.items()}


def save_triage_entry(report: Path, job_id: str, status: str, note: str = "") -> dict | None:
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("Identifiant d'offre invalide.")
    job_id = job_id.strip()
    if len(job_id) > MAX_JOB_ID_LENGTH:
        raise ValueError(f"Identifiant d'offre trop long ({MAX_JOB_ID_LENGTH} caractères maximum).")
    if not isinstance(status, str) or status not in TRIAGE_STATUSES:
        raise ValueError("Statut de triage invalide.")
    if not isinstance(note, str):
        raise ValueError("La note doit être un texte.")
    note = note.strip()
    if len(note) > 500:
        raise ValueError("La note ne peut pas dépasser 500 caractères.")
    data = read_triage(report)
    if status == "todo" and note == "":
        data.pop(job_id, None)
        entry = None
    else:
        if job_id not in data and len(data) >= MAX_TRIAGE_ENTRIES:
            raise ValueError(f"Limite de {MAX_TRIAGE_ENTRIES} entrées de triage atteinte.")
        entry = {"status": status, "note": note, "updated_at": round(time.time(), 3)}
        data[job_id] = entry
    path = triage_path(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    with _FILE_CACHE_LOCK:
        _FILE_CACHE.pop(("_load_triage", str(path.resolve())), None)
    return entry


def _load_jobs(path: Path) -> list:
    jobs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            job = json.loads(line)
            if isinstance(job, dict) and "job_id" in job:
                jobs.setdefault(str(job["job_id"]), job)
        except (ValueError, KeyError, TypeError):
            continue
    return list(jobs.values())


def read_jobs(path, include_senior=False):
    cached = _cached_read(path, _load_jobs, default=[])
    return [dict(job) for job in cached if include_senior or not is_senior(job)]


def _load_analysis_bundle(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return [], [], []
    analyses = data.get("analyses") if isinstance(data.get("analyses"), list) else []
    echecs = data.get("echecs") if isinstance(data.get("echecs"), list) else []
    exclusions = data.get("exclusions") if isinstance(data.get("exclusions"), list) else []
    return analyses, echecs, exclusions


def read_analysis_bundle(report: Path):
    return _cached_read(report.with_suffix(".json"), _load_analysis_bundle, default=([], [], []))


def read_analyses(report: Path) -> dict:
    analyses_list, _, _ = read_analysis_bundle(report)
    analyses = {}
    for row in analyses_list:
        if not isinstance(row, dict):
            continue
        try:
            analyses[str(row["offre"]["job_id"])] = dict(row["analyse"])
        except (KeyError, TypeError, ValueError):
            continue
    return analyses


def _invalidate_container_cache(container=None):
    with _CONTAINER_CACHE_LOCK:
        if container is None:
            _CONTAINER_CACHE.clear()
        else:
            _CONTAINER_CACHE.pop(container, None)


def container_running(container):
    if not container:
        return False
    now = time.monotonic()
    with _CONTAINER_CACHE_LOCK:
        cached = _CONTAINER_CACHE.get(container)
        if cached and now - cached[0] < CONTAINER_CACHE_TTL:
            return cached[1]
    try:
        result = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", container],
                                capture_output=True, text=True, timeout=3, check=False)
        running = result.returncode == 0 and result.stdout.strip() == "true"
    except (OSError, subprocess.TimeoutExpired):
        running = False
    with _CONTAINER_CACHE_LOCK:
        _CONTAINER_CACHE[container] = (time.monotonic(), running)
    return running


def remove_stopped_container(container):
    if not container:
        return
    try:
        inspect = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", container],
                                 capture_output=True, text=True, timeout=3, check=False)
        if inspect.returncode == 0 and inspect.stdout.strip().lower() != "true":
            subprocess.run(["docker", "rm", "-f", container],
                           capture_output=True, text=True, timeout=10, check=False)
            _invalidate_container_cache(container)
    except (OSError, subprocess.TimeoutExpired):
        pass


def read_search(jobs_path):
    try:
        saved = json.loads(jobs_path.resolve().with_suffix(".search.json").read_text(encoding="utf-8"))
        return saved if isinstance(saved, dict) else {}
    except (OSError, UnicodeError, ValueError):
        return {}


def search_state(jobs_path, running, analysing):
    saved = read_search(jobs_path)
    if running and saved.get("status") != "running":
        return {"status": "running", "message": "Recherche en cours.", "completed": 0, "total": 0,
                "new_jobs": 0, "can_start": False, "elapsed_seconds": None, "remaining_seconds": None,
                "discovered_jobs": None, "last_query": "", "recent_new_jobs": []}
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
    source_label = "Indeed AU" if saved.get("source") == "indeed" else "SEEK"
    if status == "running":
        message = f"Recherche {source_label} en cours."
    elif status == "finished":
        message = f"Recherche {source_label} terminée. Nouvelles annonces collectées : {new_jobs}."
    elif status == "failed":
        message = f"Recherche {source_label} interrompue ou incomplète. Les offres enregistrées restent disponibles."
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
    profile_text = _cached_read(profile, _load_text, default="") if profile else ""
    fingerprint = profile_fingerprint(profile_text)
    all_jobs = read_jobs(jobs_path, include_senior=True)
    analyses_list, echecs_list, exclusions_list = read_analysis_bundle(report)
    analyses = {}
    for row in analyses_list:
        if not isinstance(row, dict):
            continue
        try:
            job_id = str(row["offre"]["job_id"])
            analysis = row["analyse"]
        except (KeyError, TypeError):
            continue
        if not isinstance(analysis, dict):
            continue
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
        for field in ("points_forts", "points_a_verifier"):
            if isinstance(updated.get(field), list):
                updated[field] = [item for item in updated[field]
                                  if isinstance(item, str) and not STALE_LOCATION_LEAK.search(item)]
        if isinstance(updated.get("resume"), str) and STALE_LOCATION_LEAK.search(updated["resume"]):
            updated["resume"] = "Consulte les points forts et les exigences de l'annonce ci-dessous."
        description = row.get("description") if isinstance(row.get("description"), str) else ""
        if updated.get("contract_duration") is None:
            updated["contract_duration"] = contract_duration(description)
        if updated.get("work_mode") is None:
            updated["work_mode"] = work_mode(description)
        if updated.get("recruiter_contacts") is None:
            updated["recruiter_contacts"] = recruiter_contacts(description)
        updated["whv_flags"] = whv_flags(updated)
        analyses[job_id] = updated
    running = container_running(container)
    searching = container_running(search_container)
    excluded_ids = {job_id for job_id, analysis in analyses.items()
                    if experience_exclusion(analysis.get("preuve_experience", ""))}
    for row in exclusions_list:
        if not isinstance(row, dict):
            continue
        try:
            ex_id = str(row["job"]["job_id"])
        except (KeyError, TypeError):
            continue
        if experience_exclusion(row.get("reason", "")):
            excluded_ids.add(ex_id)
    failed_ids = set()
    terminal_failed_ids = set()
    for row in echecs_list:
        if not isinstance(row, dict):
            continue
        try:
            fail_id = str(row["job"]["job_id"])
        except (KeyError, TypeError):
            continue
        if row.get("terminal") is True:
            terminal_failed_ids.add(fail_id)
        else:
            failed_ids.add(fail_id)
    eligible = [job for job in all_jobs if not is_senior(job) and is_target_role(job)
                and str(job["job_id"]) not in excluded_ids]
    for job in eligible:
        job["role_category"] = role_category(job)
        job["employer_tag"] = employer_tag(job)
        job["source"] = "indeed" if job.get("source") == "indeed" or str(job["job_id"]).startswith("in-") else "seek"
        job.pop("description", None)

    def _dedup_rank(job):
        jid = str(job["job_id"])
        analysis = analyses.get(jid)
        return (job["source"] == "seek", analysis is not None, bool(analysis and not analysis["score_obsolete"]))

    jobs = []
    seen_dedup = {}
    for job in eligible:
        dedup_key = normalized_dedup_key(job.get("job_title", ""), job.get("business_name", ""))
        if dedup_key is None:
            jobs.append(job)
            continue
        existing_idx = seen_dedup.get(dedup_key)
        if existing_idx is None:
            seen_dedup[dedup_key] = len(jobs)
            jobs.append(job)
        elif _dedup_rank(job) > _dedup_rank(jobs[existing_idx]):
            jobs[existing_idx] = job

    visible_ids = {str(job["job_id"]) for job in jobs}
    analyses = {job_id: analysis for job_id, analysis in analyses.items() if job_id in visible_ids}
    has_missing_ai = any(analysis.get("modele") == AI_UNAVAILABLE_MODEL for analysis in analyses.values())
    ollama_up = container_running("seekspider-ollama") if has_missing_ai else False
    ai_pending = 0
    for analysis in analyses.values():
        needs_ai = bool(ollama_up and analysis.get("modele") == AI_UNAVAILABLE_MODEL)
        analysis["ai_pending"] = needs_ai
        if needs_ai:
            ai_pending += 1
    current_ids = {job_id for job_id, analysis in analyses.items() if not analysis["score_obsolete"]}
    terminal_visible = (terminal_failed_ids & visible_ids) - set(analyses)
    failures = len((failed_ids & visible_ids) - current_ids)
    completed = len(current_ids)
    stale = len(analyses) - completed
    pending = len(jobs) - completed - len(terminal_visible)
    if running:
        status, message = "running", "Analyse locale en cours"
    elif all_jobs and pending == 0 and not failures and not ai_pending:
        status, message = "finished", "Analyse terminée ; consulte les résultats"
    else:
        status = "stopped"
        if pending or failures or ai_pending:
            parts = [f"{stale} score(s) à recalculer", f"{pending - stale} offre(s) à analyser", f"{failures} échec(s) à réessayer"]
            if ai_pending:
                parts.append(f"{ai_pending} note(s) IA à générer")
            message = "Analyse en pause : " + ", ".join(parts)
        else:
            message = "Analyse en pause ; les résultats enregistrés sont conservés"
    triage = {job_id: entry for job_id, entry in read_triage(report).items() if job_id in visible_ids}
    return {"jobs": jobs, "analyses": analyses, "triage": triage, "profile": profile_summary(profile_text),
            "search": search_state(jobs_path, searching, running),
            "progress": {"completed": completed, "total": len(jobs), "status": status, "message": message,
                         "model": DEFAULT_MODEL,
                         "excluded": len(all_jobs) - len(jobs),
                         "stale": stale,
                         "pending": pending,
                         "failed": failures,
                         "ai_pending": ai_pending,
                         "can_start": bool(profile_text.strip() and jobs and not running and not searching and (pending > 0 or ai_pending > 0)),
                         "can_stop": running}}


class SeekSpiderServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_server(jobs: Path, report: Path, total: int = 20, profile: Path | None = None,
                  port: int = 8765, container: str = "seekspider-ranking",
                  search_container: str = "seekspider-search") -> SeekSpiderServer:
    html = Path(__file__).parent / "local_ui/index.html"
    project = Path(__file__).resolve().parent
    jobs_path = jobs.resolve()
    triage_lock = threading.Lock()
    task_lock = threading.Lock()
    task_state = {"busy": False, "handoff_pending": False, "handoff_message": ""}

    def current_state():
        return state(jobs, report, total, container, profile, search_container)

    def start_analysis(collected=None):
        if not profile:
            raise ValueError("Profil CV manquant.")
        remove_stopped_container(container)
        network = ["--network", "container:seekspider-ollama"] if container_running("seekspider-ollama") else []
        extra_mount = ["-v", f"{collected}:/private/collected.json:ro"] if collected else []
        subset = ["--collected", "/private/collected.json"] if collected else []
        command = ["docker", "run", "-d", "--rm", "--name", container,
            *DOCKER_HARDENING, *network, "--entrypoint", "python",
            "-v", f"{project}:/src:ro", "-v", f"{jobs_path}:/data/jobs.jsonl:ro",
            "-v", f"{report.resolve().parent}:/results",
            "-v", f"{profile.resolve()}:/private/profile.txt:ro", *extra_mount, "seekspider-run",
            "/src/local_rank.py", "/data/jobs.jsonl", f"/results/{report.name}",
            "--profile", "/private/profile.txt", "--model", DEFAULT_MODEL, "--limit", "1000000", "--resume", *subset]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError("Impossible de lancer l'analyse. Vérifie Docker et la présence de l'image seekspider-run.")
        _invalidate_container_cache(container)

    def analyse_after_search(worker_id):
        message = ""
        acquired = False
        try:
            result = subprocess.run(["docker", "wait", worker_id], capture_output=True, text=True, timeout=420)
            _invalidate_container_cache(search_container)
            if result.returncode or result.stdout.strip() != "0":
                return
            with task_lock:
                if task_state["busy"]:
                    message = "Analyse automatique en attente. Utilisez « Démarrer ou reprendre »."
                    return
                task_state["busy"] = True
                acquired = True
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
            with task_lock:
                if acquired:
                    task_state["busy"] = False
                task_state.update(handoff_pending=False, handoff_message=message)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(10.0)
            super().setup()

        def end_headers(self):
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            super().end_headers()

        def log_message(self, fmt, *log_args):
            if (len(log_args) >= 2 and getattr(self, "command", "") == "GET"
                    and urlparse(getattr(self, "path", "")).path in ("/api/state", "/health")
                    and str(log_args[1]) in ("200", "204")):
                return
            super().log_message(fmt, *log_args)

        def _valid_host(self):
            bound_port = self.server.server_port
            if self.headers.get("Host", "").lower() not in {f"localhost:{bound_port}", f"127.0.0.1:{bound_port}"}:
                self.send_error(403)
                return False
            return True

        def do_GET(self):
            if not self._valid_host():
                return
            route = urlparse(self.path).path
            if route == "/health":
                content, content_type = b'{"ok": true}', "application/json; charset=utf-8"
            elif route == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            elif route == "/":
                content, content_type = html.read_bytes(), "text/html; charset=utf-8"
            elif route == "/api/state":
                payload = current_state()
                with task_lock:
                    pending, handoff_message = task_state["handoff_pending"], task_state["handoff_message"]
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
            self.end_headers()
            self.wfile.write(content)

        def do_POST(self):
            if not self._valid_host():
                return
            bound_port = self.server.server_port
            origin = self.headers.get("Origin", "")
            allowed = {f"http://localhost:{bound_port}", f"http://127.0.0.1:{bound_port}"}
            if origin not in allowed or self.headers.get_content_type() != "application/json":
                self.send_error(403)
                return
            try:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except (TypeError, ValueError) as exc:
                    raise ValueError("En-tête Content-Length invalide.") from exc
                if length > 4096 or length < 0:
                    raise ValueError("Requête trop volumineuse.")
                body = self.rfile.read(length)
                route = urlparse(self.path).path
                payload, code = {"ok": True}, 200
                if route == "/api/triage":
                    try:
                        data = json.loads(body.decode("utf-8")) if body else None
                    except (UnicodeDecodeError, ValueError) as exc:
                        raise ValueError("Corps JSON invalide.") from exc
                    if not isinstance(data, dict):
                        raise ValueError("Corps JSON invalide.")
                    with triage_lock:
                        entry = save_triage_entry(
                            report,
                            data.get("job_id"),
                            data.get("status"),
                            data.get("note", ""),
                        )
                    payload = {"ok": True, "triage": entry}
                elif route in ("/api/search/start", "/api/search/indeed/start", "/api/analysis/start", "/api/analysis/stop"):
                    with task_lock:
                        if task_state["busy"]:
                            raise ValueError("Une opération est déjà en cours. Réessaie dans quelques secondes.")
                        if route != "/api/analysis/stop" and task_state["handoff_pending"]:
                            raise ValueError("Une recherche ou une analyse est déjà en cours.")
                        task_state["busy"] = True
                    try:
                        _invalidate_container_cache()
                        if route in ("/api/search/start", "/api/search/indeed/start"):
                            if container_running(container) or container_running(search_container):
                                raise ValueError("Une recherche ou une analyse est déjà en cours.")
                            jobs_path.parent.mkdir(parents=True, exist_ok=True)
                            remove_stopped_container(search_container)
                            script = "/src/indeed_search.py" if route == "/api/search/indeed/start" else "/src/targeted_search.py"
                            command = ["docker", "run", "-d", "--rm", "--name", search_container,
                                *DOCKER_HARDENING, "--entrypoint", "python",
                                "-v", f"{project}:/src:ro", "-v", f"{jobs_path.parent}:/jobs",
                                "seekspider-run", script, f"/jobs/{jobs_path.name}", "--merge"]
                            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                            if result.returncode:
                                raise ValueError("Impossible de lancer la recherche. Vérifie Docker et l’image seekspider-run.")
                            _invalidate_container_cache(search_container)
                            with task_lock:
                                task_state.update(handoff_pending=True, handoff_message="")
                            threading.Thread(target=analyse_after_search, args=(result.stdout.strip(),), daemon=True).start()
                        elif route == "/api/analysis/start":
                            if not current_state()["progress"]["can_start"]:
                                raise ValueError("Démarrage impossible : profil manquant, aucune offre restante ou une tâche est déjà active.")
                            start_analysis()
                        elif route == "/api/analysis/stop":
                            if not container_running(container):
                                raise ValueError("Aucune analyse active.")
                            result = subprocess.run(["docker", "stop", "-t", "15", container], capture_output=True, text=True, timeout=25)
                            if result.returncode:
                                raise ValueError("Impossible d'arrêter l'analyse.")
                            _invalidate_container_cache(container)
                    finally:
                        with task_lock:
                            task_state["busy"] = False
                else:
                    self.send_error(404)
                    return
            except ValueError as exc:
                payload, code = {"error": str(exc)}, 400
            except subprocess.TimeoutExpired:
                payload, code = {"error": "Délai d'attente dépassé lors de la communication avec Docker."}, 504
            except OSError:
                payload, code = {"error": "Erreur locale lors du traitement de la requête."}, 500
            content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return SeekSpiderServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--total", type=int, default=20)
    parser.add_argument("--container", default="")
    parser.add_argument("--profile", type=Path, help="Profil ou CV texte local pour l'analyse")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    httpd = create_server(args.jobs, args.report, args.total, args.profile, args.port)
    print(f"SeekSpider : http://127.0.0.1:{args.port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
