"""Collect recent Indeed Australia tech offers via python-jobspy without touching SEEK scraping."""
import argparse
import json
import math
import re
import time
from pathlib import Path
from tempfile import TemporaryDirectory

QUERIES = [
    "AWS Cloud Engineer",
    "Cloud Engineer",
    "DevOps Engineer",
    "Site Reliability Engineer",
    "Cloud Support Engineer",
    "Platform Engineer",
    "Cloud Operations Engineer",
    "Infrastructure Engineer",
    "Systems Engineer",
    "Linux System Administrator",
    "IT Operations Engineer",
    "Production Support Engineer",
    "IT Support Engineer",
    "Technical Support Engineer",
    "NOC Engineer",
    "AI Engineer MLOps",
]

WORK_TYPE_MAP = {
    "fulltime": "Full time",
    "full-time": "Full time",
    "full_time": "Full time",
    "parttime": "Part time",
    "part-time": "Part time",
    "part_time": "Part time",
    "contract": "Contract/Temp",
    "temporary": "Contract/Temp",
    "temp": "Contract/Temp",
    "casual": "Casual/Vacation",
    "internship": "Contract/Temp",
}


def clean_str(value):
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in ("nan", "none", "nat") else text


def dedup_key(title, company):
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", clean_str(s).lower()).strip()
    t, c = norm(title), norm(company)
    return (t, c) if t and c else None


def format_work_type(raw):
    text = clean_str(raw)
    if not text:
        return ""
    parts = [part.strip().lower() for part in re.split(r"[,;/]", text) if part.strip()]
    for part in parts:
        if part in ("contract", "temporary", "temp"):
            return "Contract/Temp"
    return WORK_TYPE_MAP.get(parts[0], text) if parts else ""


def format_pay_range(currency, min_amount, max_amount, interval):
    def num(v):
        if v is None or (isinstance(v, float) and (math.isnan(v) or not math.isfinite(v))):
            return None
        try:
            f = float(v)
            return f if math.isfinite(f) and f > 0 else None
        except (TypeError, ValueError):
            return None

    lo, hi = num(min_amount), num(max_amount)
    if lo is None and hi is None:
        return ""
    cur = clean_str(currency) or "AUD"
    unit = clean_str(interval)
    fmt = lambda x: f"{int(round(x)):,}" if x >= 100 else f"{x:g}"
    span = f"{fmt(lo)} - {fmt(hi)}" if lo is not None and hi is not None and lo != hi else fmt(lo or hi)
    return f"{cur} {span}" + (f" ({unit})" if unit else "")


def normalize_row(row, query):
    raw_id = clean_str(row.get("id"))
    title = clean_str(row.get("title"))
    url = clean_str(row.get("job_url"))
    if not raw_id or not title or not url:
        return None
    job_id = raw_id if raw_id.startswith("in-") else f"in-{raw_id}"
    posted = clean_str(row.get("date_posted"))
    if hasattr(row.get("date_posted"), "isoformat"):
        posted = row["date_posted"].isoformat()
    desc = clean_str(row.get("description"))
    return {
        "job_id": job_id,
        "source": "indeed",
        "job_title": title,
        "business_name": clean_str(row.get("company")),
        "area": clean_str(row.get("location")) or "Australia",
        "region": "Australia",
        "work_type": format_work_type(row.get("job_type")),
        "pay_range": format_pay_range(
            row.get("currency"), row.get("min_amount"), row.get("max_amount"), row.get("interval")
        ),
        "url": url,
        "posted_date": posted,
        "query": query,
        "description": desc[:25000],
    }


def index_jobs(path):
    jobs = {}
    keys = set()
    if path.is_file():
        with path.open(encoding="utf-8") as feed:
            for line in feed:
                if line.strip():
                    job = json.loads(line)
                    jobs.setdefault(str(job["job_id"]), job)
                    key = dedup_key(job.get("job_title"), job.get("business_name"))
                    if key:
                        keys.add(key)
    return jobs, keys


class IndeedProgress:
    def __init__(self, path=None, total=len(QUERIES)):
        self.path = path
        self.total = total
        self.started_at = time.time()
        self.completed = 0
        self.last_query = ""
        self.known_ids = set()
        self.known_keys = set()
        self.discovered_jobs = 0
        self.recent_new_jobs = []

    def record_page(self, query, items):
        new_items = []
        preview = []
        for item in items:
            job_id = str(item["job_id"])
            key = dedup_key(item.get("job_title"), item.get("business_name"))
            if job_id in self.known_ids or (key and key in self.known_keys):
                continue
            self.known_ids.add(job_id)
            if key:
                self.known_keys.add(key)
            new_items.append(item)
            if len(preview) < 4 and item.get("job_title"):
                preview.append({field: str(item.get(field) or "")[:180]
                                for field in ("job_title", "business_name", "area")})
        self.discovered_jobs += len(new_items)
        self.recent_new_jobs = (preview + self.recent_new_jobs)[:4]
        self.completed += 1
        self.last_query = query
        self.save("running")
        return new_items

    def save(self, status, added_job_ids=()):
        if not self.path:
            return
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "source": "indeed",
            "status": status, "completed": self.completed, "total": self.total,
            "new_jobs": len(added_job_ids), "added_job_ids": list(added_job_ids),
            "started_at": self.started_at, "updated_at": time.time(),
            "discovered_jobs": self.discovered_jobs, "last_query": self.last_query,
            "recent_new_jobs": self.recent_new_jobs,
        }, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)


def publish_feed(staged, output, merge):
    if not merge:
        staged.replace(output)
        return []
    existing, existing_keys = index_jobs(output)
    staged_jobs, _ = index_jobs(staged)
    added = {}
    for job_id, job in staged_jobs.items():
        key = dedup_key(job.get("job_title"), job.get("business_name"))
        if job_id in existing or (key and key in existing_keys):
            continue
        added[job_id] = job
        if key:
            existing_keys.add(key)
    if not added:
        return []
    existing.update(added)
    with staged.open("w", encoding="utf-8") as feed:
        for job in existing.values():
            feed.write(json.dumps(job, ensure_ascii=False) + "\n")
    staged.replace(output)
    return list(added)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Fichier JSONL de sortie")
    parser.add_argument("--merge", action="store_true", help="Conserver les offres existantes et suivre la progression")
    parser.add_argument("--hours-old", type=int, default=168, help="Fraîcheur maximale en heures (défaut 168 = 7j)")
    parser.add_argument("--results-per-query", type=int, default=20)
    args = parser.parse_args()

    from jobspy import scrape_jobs

    args.output.parent.mkdir(parents=True, exist_ok=True)
    progress = IndeedProgress(args.output.with_suffix(".search.json") if args.merge else None, total=len(QUERIES))
    progress.save("running")
    succeeded_queries = 0
    try:
        if args.merge:
            existing, existing_keys = index_jobs(args.output)
            progress.known_ids.update(existing)
            progress.known_keys.update(existing_keys)
        with TemporaryDirectory(dir=args.output.parent, prefix=".indeed-") as work:
            staged = Path(work) / "jobs.jsonl"
            with staged.open("w", encoding="utf-8") as feed:
                for idx, query in enumerate(QUERIES):
                    items = []
                    try:
                        df = scrape_jobs(
                            site_name=["indeed"],
                            search_term=query,
                            location="Australia",
                            results_wanted=args.results_per_query,
                            hours_old=args.hours_old,
                            country_indeed="Australia",
                            verbose=0,
                        )
                        succeeded_queries += 1
                        if df is not None and len(df):
                            for row in df.to_dict(orient="records"):
                                item = normalize_row(row, query)
                                if item:
                                    items.append(item)
                    except Exception as exc:
                        print(f"Indeed query failed ({query}): {exc}", flush=True)
                    new_items = progress.record_page(query, items)
                    for item in (new_items if args.merge else items):
                        feed.write(json.dumps(item, ensure_ascii=False) + "\n")
                    if idx + 1 < len(QUERIES):
                        time.sleep(1.5)
            if succeeded_queries == 0:
                raise ValueError("Collecte Indeed AU impossible (aucune requête réussie).")
            added_job_ids = publish_feed(staged, args.output, args.merge)
        progress.save("finished", added_job_ids)
        print(f"Indeed AU terminé : {len(added_job_ids)} nouvelle(s) offre(s) ajoutée(s).", flush=True)
    except Exception:
        progress.save("failed")
        raise


if __name__ == "__main__":
    main()
