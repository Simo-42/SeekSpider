"""Collect the first SEEK search page for each target title, without a database."""
import argparse
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode

from scrapy import Request
from scrapy.crawler import CrawlerProcess
from SeekSpider.spiders.seek import SeekSpider

TITLES = [
    "AWS Cloud Engineer", "Cloud Engineer", "Junior DevOps Engineer", "DevOps Engineer",
    "Site Reliability Engineer", "Cloud Support Engineer", "Cloud Support Associate",
    "Platform Engineer", "Cloud Operations Engineer", "Infrastructure Automation Engineer",
    "CI/CD Engineer", "Observability Engineer", "Junior Cloud Architect",
    "Infrastructure Engineer", "Systems Engineer", "Linux System Administrator",
    "ICT Systems Administrator", "IT Operations Engineer", "IT Operations Analyst",
    "Production Support Engineer", "Application Support Engineer", "Infrastructure Support Engineer",
    "Cloud Security Engineer", "Infrastructure Security Engineer", "Technical Support Engineer",
    "IT Support Engineer", "Level 2 Support Engineer", "Level 3 Support Engineer", "NOC Engineer",
    "NOC Analyst", "MSP Systems Engineer", "ICT Support Officer", "Service Desk Analyst",
    "Desktop Support Engineer", "Data Center Technician", "IT Field Services Engineer",
    "Junior AI Engineer", "MLOps Engineer", "AI Infrastructure Engineer", "GenAI Engineer",
    "AI Platform Engineer", "LLMOps Engineer",
]


class SearchProgress:
    def __init__(self, path=None):
        self.path = path
        self.started_at = time.time()
        self.completed = 0
        self.last_query = ""
        self.known_ids = set()
        self.discovered_jobs = 0
        self.recent_new_jobs = []

    def record_page(self, query, items):
        new_items = []
        preview = []
        for item in items:
            job_id = str(item["job_id"])
            if job_id in self.known_ids:
                continue
            self.known_ids.add(job_id)
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
            "status": status, "completed": self.completed, "total": len(TITLES),
            "new_jobs": len(added_job_ids), "added_job_ids": list(added_job_ids),
            "started_at": self.started_at, "updated_at": time.time(),
            "discovered_jobs": self.discovered_jobs, "last_query": self.last_query,
            "recent_new_jobs": self.recent_new_jobs,
        }, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)


class TargetedSeek(SeekSpider):
    name = "targeted_seek"

    def __init__(self, progress=None, **kwargs):
        super().__init__(**kwargs)
        self.progress = progress if progress is not None else SearchProgress()

    def start_requests(self):
        for title in TITLES:
            params = {"siteKey": "AU-Main", "sourcesystem": "houston", "where": "Australia",
                      "keywords": title, "page": 1, "locale": "en-AU"}
            yield Request(self.base_url + "?" + urlencode(params), headers=self.headers,
                          cb_kwargs={"query": title})

    def parse(self, response, query):
        jobs = response.json()["data"]
        if not isinstance(jobs, list):
            raise ValueError(f"Réponse SEEK invalide : {query}")
        items = []
        for job in jobs:
            item = dict(self.parse_job(job).meta["item"])
            item["region"] = "Australia"
            item["query"] = query
            items.append(item)
        new_items = self.progress.record_page(query, items)
        yield from new_items if self.progress.path else items

    def closed(self, reason):
        pass  # No database or AI processing during this export.


def index_jobs(path):
    jobs = {}
    if path.is_file():
        with path.open(encoding="utf-8") as feed:
            for line in feed:
                if line.strip():
                    job = json.loads(line)
                    jobs.setdefault(str(job["job_id"]), job)
    return jobs


def publish_feed(staged, output, merge):
    if not merge:
        staged.replace(output)
        return []
    existing = index_jobs(output)
    new = {job_id: job for job_id, job in index_jobs(staged).items() if job_id not in existing}
    if not new:
        return []
    existing.update(new)
    with staged.open("w", encoding="utf-8") as feed:
        for job in existing.values():
            feed.write(json.dumps(job, ensure_ascii=False) + "\n")
    staged.replace(output)
    return list(new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Fichier JSONL de sortie")
    parser.add_argument("--merge", action="store_true", help="Conserver les offres précédentes et suivre la progression locale")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    progress = SearchProgress(args.output.with_suffix(".search.json") if args.merge else None)
    progress.save("running")
    try:
        if args.merge:
            progress.known_ids.update(index_jobs(args.output))
        # Keep the existing feed readable until all searches have succeeded.
        with TemporaryDirectory(dir=args.output.parent, prefix=".seekspider-") as work:
            staged = Path(work) / "jobs.jsonl"
            staged.touch()
            process = CrawlerProcess({"ITEM_PIPELINES": {},
                "FEEDS": {staged: {"format": "jsonlines", "overwrite": True}},
                "DOWNLOAD_DELAY": 2, "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
                "DOWNLOAD_TIMEOUT": 25, "CLOSESPIDER_TIMEOUT": 360,
                "LOG_LEVEL": "INFO", "TELNETCONSOLE_ENABLED": False})
            crawler = process.create_crawler(TargetedSeek)
            process.crawl(crawler, progress=progress)
            process.start()
            if progress.completed != len(TITLES) or crawler.stats.get_value("finish_reason") != "finished":
                raise ValueError("Collecte SEEK incomplète ; export précédent conservé.")
            added_job_ids = publish_feed(staged, args.output, args.merge)
        progress.save("finished", added_job_ids)
    except Exception:
        progress.save("failed")
        raise


if __name__ == "__main__":
    main()

