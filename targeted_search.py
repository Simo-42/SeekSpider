"""Collect the first SEEK search page for each target title, without a database."""
import argparse
import json
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


class TargetedSeek(SeekSpider):
    name = "targeted_seek"

    def __init__(self, progress=None, **kwargs):
        super().__init__(**kwargs)
        self.progress = progress

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
        for job in jobs:
            item = dict(self.parse_job(job).meta["item"])
            item["region"] = "Australia"
            item["query"] = query
            yield item
        stats = self.crawler.stats
        stats.inc_value("targeted_search/completed")
        write_progress(self.progress, "running", stats.get_value("targeted_search/completed"))

    def closed(self, reason):
        pass  # No database or AI processing during this export.



def write_progress(path, status, completed, new_jobs=0):
    if path:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "status": status, "completed": completed, "total": len(TITLES), "new_jobs": new_jobs,
        }), encoding="utf-8")
        temporary.replace(path)


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
        return 0
    existing = index_jobs(output)
    fresh = index_jobs(staged)
    new_jobs = len(fresh.keys() - existing.keys())
    if not fresh:
        return 0
    existing.update(fresh)
    with staged.open("w", encoding="utf-8") as feed:
        for job in existing.values():
            feed.write(json.dumps(job, ensure_ascii=False) + "\n")
    staged.replace(output)
    return new_jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Fichier JSONL de sortie")
    parser.add_argument("--merge", action="store_true", help="Conserver les offres précédentes et suivre la progression locale")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    progress = args.output.with_suffix(".search.json") if args.merge else None
    completed = 0
    write_progress(progress, "running", completed)
    try:
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
            completed = crawler.stats.get_value("targeted_search/completed", 0)
            if completed != len(TITLES) or crawler.stats.get_value("finish_reason") != "finished":
                raise ValueError("Collecte SEEK incomplète ; export précédent conservé.")
            new_jobs = publish_feed(staged, args.output, args.merge)
        write_progress(progress, "finished", completed, new_jobs)
    except Exception:
        write_progress(progress, "failed", completed)
        raise


if __name__ == "__main__":
    main()

