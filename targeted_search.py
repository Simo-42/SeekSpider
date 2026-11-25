"""Collect the first SEEK search page for each target title, without a database."""
import argparse
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

    def start_requests(self):
        for title in TITLES:
            params = {"siteKey": "AU-Main", "sourcesystem": "houston", "where": "Australia",
                      "keywords": title, "page": 1, "locale": "en-AU"}
            yield Request(self.base_url + "?" + urlencode(params), headers=self.headers,
                          cb_kwargs={"query": title})

    def parse(self, response, query):
        for job in response.json().get("data", []):
            item = dict(self.parse_job(job).meta["item"])
            item["region"] = "Australia"
            item["query"] = query
            yield item

    def closed(self, reason):
        pass  # No database or AI processing during this export.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="JSONL output path; overwritten on each run")
    args = parser.parse_args()
    process = CrawlerProcess({"ITEM_PIPELINES": {},
        "FEEDS": {args.output: {"format": "jsonlines", "overwrite": True}},
        "DOWNLOAD_DELAY": 2, "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "LOG_LEVEL": "INFO", "TELNETCONSOLE_ENABLED": False})
    process.crawl(TargetedSeek)
    process.start()


if __name__ == "__main__":
    main()

