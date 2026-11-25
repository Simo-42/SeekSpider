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
    assert [job["job_id"] for job in rank.select_jobs(path, 20)] == ["2"]


def test_role_families_are_prioritized_and_noise_is_removed(tmp_path):
    jobs = [{"job_id": "1", "job_title": "MLOps Engineer", "area": "Sydney NSW"},
            {"job_id": "2", "job_title": "NOC Analyst", "area": "Sydney NSW"},
            {"job_id": "3", "job_title": "Cloud Operations Engineer", "area": "Perth WA"},
            {"job_id": "4", "job_title": "Engineer Mining (Mt Holland)", "area": "Perth WA"},
            {"job_id": "5", "job_title": "Infrastructure Engineer", "area": "Sydney NSW"}]
    path = tmp_path / "jobs.jsonl"
    path.write_text("\n".join(map(json.dumps, jobs)), encoding="utf-8")
    assert [job["job_id"] for job in rank.select_jobs(path, 20)] == ["5", "3", "2", "1"]


def test_senior_title_variants_exclude_without_hiding_junior_titles():
    for title in ("Principal Cloud Engineer", "Staff DevOps Engineer", "Lead SRE", "IT Operations Manager",
                  "AI Engineers & Engineering Leads", "Operations Support Mgr / IT Support Analyst"):
        assert rank.is_senior({"job_title": title})
    for title in ("Junior Cloud Architect", "Level 3 Support Engineer", "Cloud Engineer", "IT Leadership Analyst"):
        assert not rank.is_senior({"job_title": title})


def test_fit_score_is_deterministic_and_rewards_profile_skill_overlap():
    profile = "AWS Terraform Kubernetes Docker Linux Ansible Python Bash Grafana"
    job = {"job_title": "Cloud Engineer", "area": "Sydney NSW", "region": "Australia"}
    strong = rank.calculate_fit_score(job, "AWS Terraform Linux Kubernetes", profile)
    weak = rank.calculate_fit_score(job, "Customer service and stakeholder communication", profile)
    assert strong["score_method"] == rank.SCORE_VERSION
    assert strong["score"] > weak["score"]
    assert strong["score_role"] == 18 and strong["score_location"] == 5
    assert strong["score_skills"] == 60
    assert strong["competences_reperees"] == ["AWS", "Terraform", "Kubernetes", "Linux"]
    assert strong["score"] == 87
    assert "Aucune compétence reconnue" in weak["resume"]


def test_fit_uses_offer_skills_and_target_experience():
    profile = "AWS Terraform Kubernetes Docker Linux Ansible Python Bash Grafana Observability SRE SLO"
    job = {"job_title": "SRE", "area": "Sydney NSW", "region": "Australia"}
    description = "Grafana, observability and SLOs. No AWS experience required. Datadog is preferred."
    junior = rank.calculate_fit_score(job, description + " 2 years of experience.", profile)
    more_experienced = rank.calculate_fit_score(job, description + " 4 years of experience.", profile)
    assert junior["competences_reperees"] == ["Grafana", "Observability", "SLI/SLO"]
    assert junior["competences_manquantes"] == ["Datadog"]
    assert junior["competences_comparees"] == 4
    assert junior["score"] - more_experienced["score"] == 7


def test_unavailable_model_keeps_score_and_source_evidence():
    description = "2 years of experience with AWS. Visa sponsorship is unavailable."
    with patch.object(rank.requests, "post", side_effect=rank.requests.ConnectionError):
        result = rank.analyze({"job_title": "Cloud Engineer"}, description, "AWS", "test")
    assert result["score_skills"] > 0
    assert result["preuve_visa"] in description
    assert not result["points_forts"]


def test_description_keeps_bullet_boundaries_for_experience_filter():
    description = rank.description_text("<ul><li>Customer experience focus</li><li>5 years warranty</li><li>Minimum 2 years of experience in support</li></ul>")
    assert "Customer experience focus\n5 years warranty" in description
    assert rank.experience_exclusion(description) is None
    wrapped = rank.description_text("<p>Minimum <b>5 years’</b> experience in DevOps.</p>")
    assert rank.experience_exclusion(wrapped)
    assert rank.experience_exclusion("5 years of experience is optional.") is None
    assert rank.experience_exclusion("5 years of experience (not mandatory).") is None


def test_rejects_invented_evidence():
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": json.dumps({
                "points_forts": [], "points_a_verifier": [],
                "experience": "3 ans", "preuve_experience": "3 years experience",
                "visa_sponsoring": "Sponsoring possible", "preuve_visa": "visa sponsorship available"
            })}}

    with patch.object(rank.requests, "post", return_value=Response()):
        result = rank.analyze({"job_title": "Cloud Engineer", "area": "Sydney NSW", "region": "Australia"},
                              "Requires 3 years experience. AWS, Terraform, Linux.", "AWS Terraform Linux Python", "model")
    assert result["preuve_experience"] == "Requires 3 years experience."
    assert result["preuve_visa"] == "Aucun extrait repéré"
    assert result["visa_sponsoring"] == "Aucune mention repérée automatiquement : vérifie l'annonce."
    assert result["score_method"] == rank.SCORE_VERSION and result["score"] > 0


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
                 "Only Australian citizens are eligible.",
                 "Australian permanent residents may apply.",
                 "Applicants must hold subclass 417 or 482.",
                 "Applicants must have a valid VEVO check."):
        evidence = rank.extract_evidence(text, rank.VISA_TERMS)
        assert evidence and evidence in text
    assert "NV2" in rank.extract_evidence("Professionals with NV2 & TSPV clearances are required.", rank.CLEARANCE_TERMS)
    assert "Baseline" in rank.extract_evidence("Baseline security clearance is required.", rank.CLEARANCE_TERMS)
    assert rank.extract_evidence("Experience with security incident response.", rank.VISA_TERMS) is None
    assert rank.extract_evidence("Accepts Visa and Mastercard. We value corporate citizenship.", rank.VISA_TERMS) is None
    assert rank.extract_evidence("Equal opportunity regardless of race, color, ancestry, religion, sex, citizenship, marital status or disability.", rank.VISA_TERMS) is None
    assert rank.extract_evidence("Only Australian permanent residents may apply.", rank.VISA_TERMS)
    assert rank.extract_evidence("Baseline response time is 200 ms; submit a PR for review.", rank.CLEARANCE_TERMS) is None


def test_work_rights_and_security_clearance_evidence_are_separate():
    text = "Applicants need full working rights in Australia. NV2 security clearance is required."
    result = rank.attach_source_evidence({"resume": "NV2 guarantees a visa", "points_forts": [], "points_a_verifier": []}, text)
    assert "working rights" in result["preuve_visa"]
    assert "NV2" not in result["preuve_visa"]
    assert "NV2" in result["preuve_habilitation"]
    assert "visa" not in result["preuve_habilitation"].lower()


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
                 "A minimum of 6.5+ years of experience.",
                 "5+ years in a similar infrastructure role.",
                 "At least 5 years in DevOps is required.",
                 "5+ years designing, deploying and maintaining secure cloud infrastructure."):
        proof = rank.experience_exclusion(text)
        assert proof and proof in text
    for text in ("3-5 years of experience.", "3 to 5 years of experience.", "three to five years of experience.", "Up to 5 years of experience.",
                 "Less than 5 years of experience.", "5+ years of experience preferred.",
                 "5+ years of experience would be a bonus.",
                 "At least 5 years in DevOps would be beneficial.",
                 "Desirable:\n5+ years of experience in cloud engineering.",
                 "4 years of experience required; 5 years of experience preferred.",
                 "4 years required, 5 years would be a bonus.",
                 "4.5 years of experience required.",
                 "A 5-year contract with experienced colleagues.",
                 "A five-year warranty on the product.",
                 "An Australian consultancy with over 15 years of experience, we help businesses.",
                 "We have over 15 years of industry experience delivering cloud solutions.",
                 "Great customer experience. 5 years fixed term contract.",
                 "Our business has over 30 years of experience."):
        assert rank.experience_exclusion(text) is None, text


def test_experience_proof_ignores_company_history_and_contracts():
    for text in ("For the next 50 years.", "Our business has 30 years of experience.",
                 "Great customer experience. 5 years fixed term contract.",
                 "NEXTDC is a company, only 16 years young."):
        assert rank.experience_evidence(text) is None, text
    proof = rank.experience_evidence("Minimum 2 years of experience in IT support.")
    assert proof == "Minimum 2 years of experience in IT support."
    text = "NEXTDC is a company, only 16 years young and operating 18 data centres."
    assert rank.experience_exclusion(text) is None


def load_targeted_search():
    search_spec = importlib.util.spec_from_file_location("targeted_search", Path(__file__).resolve().parents[1] / "targeted_search.py")
    search = importlib.util.module_from_spec(search_spec)
    search_spec.loader.exec_module(search)
    return search


def test_search_targets_all_titles_and_australia():
    search = load_targeted_search()
    requests = list(search.TargetedSeek().start_requests())
    assert len(requests) == len(search.TITLES) == 42
    assert all(rank.is_target_role({"job_title": title}) for title in search.TITLES)
    queries = [parse_qs(urlparse(request.url).query) for request in requests]
    assert all(query["where"] == ["Australia"] for query in queries)
    assert {query["keywords"][0] for query in queries} == set(search.TITLES)



def test_search_merge_keeps_existing_jobs_and_ignores_duplicates(tmp_path):
    search = load_targeted_search()
    output, staged = tmp_path / "jobs.jsonl", tmp_path / "staged.jsonl"
    output.write_text('{"job_id":"1"}\n{"job_id":"2","job_title":"Old"}\n', encoding="utf-8")
    staged.write_text('{"job_id":"2","job_title":"New"}\n{"job_id":"3"}\n{"job_id":"3"}\n', encoding="utf-8")
    assert search.publish_feed(staged, output, merge=True) == 1
    assert list(search.index_jobs(output)) == ["1", "2", "3"]
    assert search.index_jobs(output)["2"]["job_title"] == "New"


def test_incomplete_search_preserves_existing_export(tmp_path):
    import pytest
    search = load_targeted_search()
    output = tmp_path / "jobs.jsonl"
    original = '{"job_id":"1"}\n'
    output.write_text(original, encoding="utf-8")
    with patch("sys.argv", ["targeted_search", str(output), "--merge"]), patch.object(search, "CrawlerProcess") as process:
        stats = {"targeted_search/completed": 2, "finish_reason": "finished"}
        process.return_value.create_crawler.return_value.stats.get_value.side_effect = stats.get
        with pytest.raises(ValueError, match="incomplète"):
            search.main()
    assert output.read_text(encoding="utf-8") == original
    progress = json.loads(output.with_suffix(".search.json").read_text())
    assert progress["status"] == "failed"
    assert progress["completed"] == 2

def test_resume_preserves_existing_and_skips_it(tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    report = tmp_path / "report.md"
    existing = {"offre": {"job_id": "1", "job_title": "Cloud"}, "analyse": {"score": 70, "score_method": rank.SCORE_VERSION, "profile_fingerprint": rank.profile_fingerprint(""), "resume": "OK", "points_forts": [], "points_a_verifier": [], "experience": "non précisé", "preuve_experience": "non précisé", "visa_sponsoring": "non précisé", "preuve_visa": "non précisé"}}
    jobs.write_text('\n'.join(json.dumps(job) for job in [existing["offre"], {"job_id": "2", "job_title": "Cloud"}, {"job_id": "3", "job_title": "Senior Cloud"}]), encoding="utf-8")
    report.with_suffix('.json').write_text(json.dumps({"analyses": [existing], "echecs": []}), encoding="utf-8")
    with patch('sys.argv', ['local_rank', str(jobs), str(report), '--resume', '--limit', '1']), \
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


def test_resume_rescores_cached_description_with_new_cv(tmp_path):
    jobs, report, profile = (tmp_path / name for name in ("jobs.jsonl", "report.md", "profile.txt"))
    job = {"job_id": "10", "job_title": "Cloud Engineer"}
    description = "Requires 2 years of experience with AWS, Azure and Terraform."
    jobs.write_text(json.dumps(job), encoding="utf-8")
    profile.write_text("Terraform", encoding="utf-8")
    old_result = rank.refresh_existing_analysis({}, job, description, "AWS")
    report.with_suffix(".json").write_text(json.dumps({"analyses": [
        {"offre": job, "analyse": old_result, "description": description}
    ]}), encoding="utf-8")
    with patch("sys.argv", ["local_rank", str(jobs), str(report), "--resume", "--profile", str(profile)]), \
         patch.object(rank.fetcher, "fetch_job_detail") as fetch, patch.object(rank, "analyze") as model:
        rank.main()
    fetch.assert_not_called()
    model.assert_not_called()
    analysis = json.loads(report.with_suffix(".json").read_text())["analyses"][0]["analyse"]
    assert analysis["competences_reperees"] == ["Terraform"]
    assert analysis["profile_fingerprint"] == rank.profile_fingerprint("Terraform")
