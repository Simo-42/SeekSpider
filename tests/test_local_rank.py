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
            {"job_id": "2", "job_title": "Duplicate", "area": "Sydney"},
            {"job_id": "3", "job_title": "SENIOR Cloud Engineer", "area": "Sydney"},
            {"job_id": "4", "job_title": "Sr. DevOps Engineer", "area": "Sydney"},
            {"job_id": "5", "job_title": "Snr SRE", "area": "Sydney"}]
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
    assert result["preuve_experience"] == "Requires 3 years experience."
    assert result["preuve_visa"] == "Aucun extrait repéré"
    assert result["visa_sponsoring"] == "Aucune mention repérée automatiquement : vérifie l'annonce."


def test_extracts_citizenship_and_never_invents_sponsorship():
    text = "Join our team. Australian citizenship is mandatory for this position, and you must maintain a security clearance. Apply today."
    result = rank.attach_source_evidence({"resume": "Visa 482 garanti", "points_forts": [], "points_a_verifier": ["Sponsoring possible", "AWS"]}, text)
    assert result["preuve_visa"] in text
    assert "citizenship is mandatory" in result["preuve_visa"]
    assert "garanti" not in result["resume"]
    assert result["points_a_verifier"] == ["AWS"]


def test_extracts_negative_and_positive_visa_mentions():
    for text in ("Applicants must have full working rights in Australia. No visa sponsorship is available.",
                 "Visa sponsorship is available for eligible applicants.",
                 "Candidates must be eligible to work in Australia.",
                 "Only Australian citizens are eligible."):
        evidence = rank.extract_evidence(text, rank.VISA_TERMS)
        assert evidence and evidence in text
    assert rank.extract_evidence("Experience with security incident response.", rank.VISA_TERMS) is None
    assert rank.extract_evidence("Accepts Visa and Mastercard. We value corporate citizenship.", rank.VISA_TERMS) is None


def test_finds_evidence_beyond_model_context():
    text = 'A' * 20000 + '. Australian citizenship is mandatory.'
    evidence = rank.extract_evidence(text, rank.VISA_TERMS)
    assert evidence == 'Australian citizenship is mandatory.'
    assert evidence in text


def test_excludes_clear_five_year_minimum_but_not_ranges_or_optional():
    for text in ("Skills & Experience 5+ years’ experience in DevOps.",
                 "At least 5 years of hands-on experience.",
                 "Minimum 5-7 years of relevant experience.",
                 "5 to 7 years of relevant experience required.",
                 "Six years of experience in cloud engineering.",
                 "A minimum of 6.5+ years of experience."):
        proof = rank.experience_exclusion(text)
        assert proof and proof in text
    for text in ("3-5 years of experience.", "3 to 5 years of experience.", "three to five years of experience.", "Up to 5 years of experience.",
                 "Less than 5 years of experience.", "5+ years of experience preferred.",
                 "4 years of experience required; 5 years of experience preferred.",
                 "4.5 years of experience required.",
                 "A 5-year contract with experienced colleagues.",
                 "A five-year warranty on the product.",
                 "An Australian consultancy with over 15 years of experience, we help businesses.",
                 "Our business has over 30 years of experience."):
        assert rank.experience_exclusion(text) is None, text


def test_search_targets_all_titles_and_australia():
    search_spec = importlib.util.spec_from_file_location("targeted_search", Path(__file__).resolve().parents[1] / "targeted_search.py")
    search = importlib.util.module_from_spec(search_spec)
    search_spec.loader.exec_module(search)
    requests = list(search.TargetedSeek().start_requests())
    assert len(requests) == len(search.TITLES) == 42
    queries = [parse_qs(urlparse(request.url).query) for request in requests]
    assert all(query["where"] == ["Australia"] for query in queries)
    assert {query["keywords"][0] for query in queries} == set(search.TITLES)


def test_resume_preserves_existing_and_skips_it(tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    report = tmp_path / "report.md"
    existing = {"offre": {"job_id": "1", "job_title": "Cloud"}, "analyse": {"score": 70, "resume": "OK", "points_forts": [], "points_a_verifier": [], "experience": "non précisé", "preuve_experience": "non précisé", "visa_sponsoring": "non précisé", "preuve_visa": "non précisé"}}
    jobs.write_text('\n'.join(json.dumps(job) for job in [existing["offre"], {"job_id": "2", "job_title": "Cloud"}, {"job_id": "3", "job_title": "Senior Cloud"}]), encoding="utf-8")
    report.with_suffix('.json').write_text(json.dumps({"analyses": [existing], "echecs": []}), encoding="utf-8")
    with patch('sys.argv', ['local_rank', str(jobs), str(report), '--resume']), \
         patch.object(rank.fetcher, 'fetch_job_detail', return_value=('<p>Cloud</p>', None, 'success')) as fetch, \
         patch.object(rank, 'analyze', return_value=existing['analyse']), \
         patch.object(rank.time, 'sleep'):
        rank.main()
    fetch.assert_called_once_with('2')
    data = json.loads(report.with_suffix('.json').read_text(encoding='utf-8'))
    assert [row['offre']['job_id'] for row in data['analyses']] == ['1', '2']


def test_exclusion_survives_resume_without_calling_model(tmp_path):
    jobs, report = tmp_path / 'jobs.jsonl', tmp_path / 'report.md'
    jobs.write_text(json.dumps({'job_id': '10', 'job_title': 'Cloud Engineer'}), encoding='utf-8')
    with patch('sys.argv', ['local_rank', str(jobs), str(report), '--resume']), \
         patch.object(rank.fetcher, 'fetch_job_detail', return_value=('<p>5+ years of cloud experience required.</p>', None, 'success')) as fetch, \
         patch.object(rank, 'analyze') as analyze, patch.object(rank.time, 'sleep'):
        rank.main()
        rank.main()
    fetch.assert_called_once_with('10')
    analyze.assert_not_called()
    data = json.loads(report.with_suffix('.json').read_text(encoding='utf-8'))
    assert len(data['exclusions']) == 1 and data['exclusions'][0]['job']['job_id'] == '10'

