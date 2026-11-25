import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

spec = importlib.util.spec_from_file_location("local_rank", Path(__file__).resolve().parents[1] / "local_rank.py")
rank = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rank)


def test_deduplicates_and_prioritizes(tmp_path):
    jobs = [{"job_id": "1", "job_title": "Other", "area": "Perth"},
            {"job_id": "2", "job_title": "Infrastructure Engineer", "area": "Sydney"},
            {"job_id": "2", "job_title": "Duplicate", "area": "Sydney"}]
    path = tmp_path / "jobs.jsonl"
    path.write_text("\n".join(map(json.dumps, jobs)), encoding="utf-8")
    assert [job["job_id"] for job in rank.select_jobs(path, 20)] == ["2", "1"]


def test_rejects_invented_evidence():
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": json.dumps({
                "score": 70, "resume": "Correct", "points_forts": [], "points_a_verifier": [],
                "experience": "3 ans", "preuve_experience": "3 years experience",
                "visa_sponsoring": "Sponsoring possible", "preuve_visa": "visa sponsorship available"
            })}}

    with patch.object(rank.requests, "post", return_value=Response()):
        result = rank.analyze({}, "Requires 3 years experience.", "profile", "model")
    assert result["preuve_experience"] == "3 years experience"
    assert result["preuve_visa"] == "non précisé"
    assert result["visa_sponsoring"] == "non précisé ou preuve non vérifiée"


def test_search_targets_all_titles_and_australia():
    search_spec = importlib.util.spec_from_file_location("targeted_search", Path(__file__).resolve().parents[1] / "targeted_search.py")
    search = importlib.util.module_from_spec(search_spec)
    search_spec.loader.exec_module(search)
    requests = list(search.TargetedSeek().start_requests())
    assert len(requests) == len(search.TITLES) == 42
    queries = [parse_qs(urlparse(request.url).query) for request in requests]
    assert all(query["where"] == ["Australia"] for query in queries)
    assert {query["keywords"][0] for query in queries} == set(search.TITLES)

