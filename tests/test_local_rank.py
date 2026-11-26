import importlib.util
import json
from pathlib import Path
from unittest.mock import ANY, patch
from urllib.parse import parse_qs, urlparse

spec = importlib.util.spec_from_file_location("local_rank", Path(__file__).resolve().parents[1] / "local_rank.py")
rank = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rank)
import job_filters


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
    assert [job["job_id"] for job in rank.select_jobs(path, 20)] == ["3", "5", "2", "1"]


def test_senior_title_variants_exclude_without_hiding_junior_titles():
    for title in ("Principal Cloud Engineer", "Staff DevOps Engineer", "Lead SRE", "IT Operations Manager",
                  "AI Engineers & Engineering Leads", "Operations Support Mgr / IT Support Analyst",
                  "EL1 DevOps Engineer", "Cloud Architect"):
        assert rank.is_senior({"job_title": title}), title
    for title in ("Junior Cloud Architect", "Level 3 Support Engineer", "Cloud Engineer", "IT Leadership Analyst"):
        assert not rank.is_senior({"job_title": title}), title


def test_fit_score_is_deterministic_and_rewards_profile_skill_overlap():
    profile = "AWS Terraform Kubernetes Docker Linux Ansible Python Bash Grafana"
    job = {"job_title": "Cloud Engineer", "area": "Sydney NSW", "region": "Australia"}
    strong = rank.calculate_fit_score(job, "AWS Terraform Linux Kubernetes", profile)
    weak = rank.calculate_fit_score(job, "Customer service and stakeholder communication", profile)
    assert strong["score_method"] == rank.SCORE_VERSION
    assert strong["score"] > weak["score"]
    assert strong["score_role"] == 20 and strong["score_location"] == 5
    assert strong["score_skills"] == 60
    assert strong["competences_reperees"] == ["AWS", "Terraform", "Kubernetes", "Linux"]
    assert strong["score"] == 89
    assert "Aucune compétence reconnue" in weak["resume"]


def test_priority_role_scoring():
    for title in ("AWS Cloud Engineer", "Cloud Engineer", "Junior DevOps Engineer",
                  "Site Reliability Engineer", "SRE", "Cloud Support Engineer",
                  "Cloud Support Associate", "Cloud Operations Engineer"):
        score = rank.calculate_fit_score({"job_title": title}, "AWS", "AWS")
        assert score["score_role"] == 20, title
    infra = rank.calculate_fit_score({"job_title": "Infrastructure Engineer"}, "AWS", "AWS")
    assert infra["score_role"] == 15


def test_whv_flags_detects_clearance_restrictions_and_placeholders():
    assert job_filters.whv_flags({
        "preuve_habilitation": "NV1 security clearance is required.",
        "preuve_visa": "Aucun extrait repéré",
    }) == {"clearance": True, "citizen_pr_risk": False, "visa_mention": False, "no_sponsorship": False}

    for excerpt in (
        "Only Australian citizens are eligible.",
        "Australian permanent residents may apply.",
        "PR only for this role.",
        "Applicants must have full working rights in Australia.",
        "No WHV candidates.",
    ):
        assert job_filters.whv_flags({"preuve_visa": excerpt}) == {
            "clearance": False, "citizen_pr_risk": True, "visa_mention": True, "no_sponsorship": False,
        }, excerpt

    for excerpt in (
        "No visa sponsorship is available.",
        "Unable to provide visa sponsorship.",
        "Sponsorship is not available for this role.",
    ):
        assert job_filters.whv_flags({"preuve_visa": excerpt}) == {
            "clearance": False, "citizen_pr_risk": False, "visa_mention": True, "no_sponsorship": True,
        }, excerpt

    assert job_filters.whv_flags({
        "preuve_visa": "Visa sponsorship is available for eligible applicants.",
        "preuve_habilitation": "Non précisé",
    }) == {"clearance": False, "citizen_pr_risk": False, "visa_mention": True, "no_sponsorship": False}

    for placeholder in (None, "", "   ", "non précisé", "Non précisé", "Aucun extrait repéré", "aucun extrait trouvé"):
        assert job_filters.whv_flags({
            "preuve_visa": placeholder,
            "preuve_habilitation": placeholder,
        }) == {"clearance": False, "citizen_pr_risk": False, "visa_mention": False, "no_sponsorship": False}, placeholder
    assert job_filters.whv_flags(None) == {
        "clearance": False, "citizen_pr_risk": False, "visa_mention": False, "no_sponsorship": False,
    }


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
    assert result["modele"] == rank.AI_UNAVAILABLE_MODEL
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
    assert search.publish_feed(staged, output, merge=True) == ["3"]
    assert list(search.index_jobs(output)) == ["1", "2", "3"]
    assert search.index_jobs(output)["2"]["job_title"] == "Old"


def test_live_search_ignores_saved_ads_and_keeps_a_small_preview(tmp_path):
    search = load_targeted_search()
    status = tmp_path / "jobs.search.json"
    progress = search.SearchProgress(status)
    progress.known_ids.add("0")
    first_page = progress.record_page("Cloud Engineer", [
        {"job_id": str(i), "job_title": f"Cloud Engineer {i}", "business_name": "Example", "area": "Sydney"}
        for i in range(6)
    ])
    progress.record_page("DevOps Engineer", [
        {"job_id": "2", "job_title": "Duplicate"},
        {"job_id": "6", "job_title": "DevOps Engineer", "description": "Never preview the description"}
    ])
    data = json.loads(status.read_text(encoding="utf-8"))
    assert [job["job_id"] for job in first_page] == ["1", "2", "3", "4", "5"]
    assert data["completed"] == 2 and data["discovered_jobs"] == 6
    assert data["last_query"] == "DevOps Engineer"
    assert len(data["recent_new_jobs"]) == 4
    assert data["recent_new_jobs"][0] == {"job_title": "DevOps Engineer", "business_name": "", "area": ""}
    progress.save("finished", added_job_ids=["6"])
    final = json.loads(status.read_text(encoding="utf-8"))
    assert final["status"] == "finished" and final["updated_at"] >= final["started_at"]
    assert final["added_job_ids"] == ["6"] and final["new_jobs"] == 1


def test_incomplete_search_preserves_existing_export(tmp_path):
    import pytest
    search = load_targeted_search()
    output = tmp_path / "jobs.jsonl"
    original = '{"job_id":"1"}\n'
    output.write_text(original, encoding="utf-8")
    with patch("sys.argv", ["targeted_search", str(output), "--merge"]), patch.object(search, "CrawlerProcess") as process:
        process.return_value.create_crawler.return_value.stats.get_value.return_value = "finished"
        def crawl(_crawler, progress):
            for query in search.TITLES[:2]:
                progress.record_page(query, [])
        process.return_value.crawl.side_effect = crawl
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
         patch.object(rank, 'analyze', return_value=existing['analyse']) as model, \
         patch.object(rank.time, 'sleep'):
        rank.main()
        rank.main()
    fetch.assert_called_once_with('2', session=ANY)
    model.assert_called_once()
    assert model.call_args.args[0]["job_id"] == "2"
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
    fetch.assert_called_once_with('10', session=ANY)
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


def test_analysis_after_search_only_processes_added_job_ids(tmp_path):
    jobs, report, collected = (tmp_path / name for name in ("jobs.jsonl", "report.md", "jobs.search.json"))
    old = {"job_id": "4", "job_title": "Cloud Support Engineer"}
    new = {"job_id": "5", "job_title": "SRE"}
    known_failure = {"job_id": "6", "job_title": "IT Support Engineer"}
    jobs.write_text("\n".join(map(json.dumps, [old, new, known_failure])), encoding="utf-8")
    collected.write_text(json.dumps({"added_job_ids": ["5"]}), encoding="utf-8")
    report.with_suffix(".json").write_text(json.dumps({
        "analyses": [], "echecs": [{"job": known_failure, "status": "timeout"}]
    }), encoding="utf-8")
    analysis = rank.refresh_existing_analysis({}, new, "AWS", "")
    with patch("sys.argv", ["local_rank", str(jobs), str(report), "--resume", "--collected", str(collected)]), \
         patch.object(rank.fetcher, "fetch_job_detail", return_value=("<p>AWS</p>", None, "success")) as fetch, \
         patch.object(rank, "analyze", return_value=analysis) as model, patch.object(rank.time, "sleep"):
        rank.main()
    fetch.assert_called_once_with("5", session=ANY)
    model.assert_called_once()
    data = json.loads(report.with_suffix(".json").read_text())
    assert [row["offre"]["job_id"] for row in data["analyses"]] == ["5"]
    assert data["echecs"][0]["job"]["job_id"] == "6"


def test_resume_retries_unavailable_ai_only_when_ollama_is_up(tmp_path):
    jobs, report = tmp_path / "jobs.jsonl", tmp_path / "report.md"
    job = {"job_id": "20", "job_title": "Cloud Engineer"}
    description = "Requires 2 years of experience with AWS and Terraform."
    jobs.write_text(json.dumps(job), encoding="utf-8")
    unavailable = rank.refresh_existing_analysis(
        {"points_forts": [], "points_a_verifier": [], "modele": rank.AI_UNAVAILABLE_MODEL},
        job, description, "",
    )
    report.with_suffix(".json").write_text(json.dumps({
        "analyses": [{"offre": job, "analyse": unavailable, "description": description}],
        "echecs": [],
    }), encoding="utf-8")

    with patch("sys.argv", ["local_rank", str(jobs), str(report), "--resume"]), \
         patch.object(rank, "ollama_available", return_value=False), \
         patch.object(rank.fetcher, "fetch_job_detail") as fetch, \
         patch.object(rank, "analyze") as model:
        rank.main()
    fetch.assert_not_called()
    model.assert_not_called()

    recovered = rank.refresh_existing_analysis(
        {"points_forts": ["Stack AWS/Terraform alignée"], "points_a_verifier": [], "modele": rank.DEFAULT_MODEL},
        job, description, "",
    )
    with patch("sys.argv", ["local_rank", str(jobs), str(report), "--resume"]), \
         patch.object(rank, "ollama_available", return_value=True), \
         patch.object(rank.fetcher, "fetch_job_detail") as fetch, \
         patch.object(rank, "analyze", return_value=recovered) as model:
        rank.main()
    fetch.assert_not_called()
    model.assert_called_once_with(job, description, "", rank.DEFAULT_MODEL)
    data = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
    assert len(data["analyses"]) == 1
    assert data["analyses"][0]["analyse"]["modele"] == rank.DEFAULT_MODEL
    assert data["analyses"][0]["analyse"]["points_forts"] == ["Stack AWS/Terraform alignée"]


def test_enriched_skill_patterns_match_vpc_networking_and_aws_services():
    profile = "AWS (EC2, RDS, IAM, VPC, S3, SSM), Docker Compose, NGINX with TLS, OAuth2, Agile Scrum"
    job = {"job_title": "Cloud Operations Engineer", "area": "Sydney NSW", "region": "Australia"}
    score = rank.calculate_fit_score(
        job, "Manage EC2, IAM, S3, VPC networking, CloudFormation and EKS clusters.", profile
    )
    assert set(score["competences_reperees"]) == {"EC2", "IAM", "S3", "Networking"}
    assert set(score["competences_manquantes"]) == {"CloudFormation", "EKS / ECS"}


def test_refresh_ai_updates_cached_offers_above_min_score_without_fetching(tmp_path):
    jobs, report = tmp_path / "jobs.jsonl", tmp_path / "report.md"
    high = {"job_id": "30", "job_title": "Cloud Engineer", "area": "Sydney NSW", "region": "Australia"}
    low = {"job_id": "31", "job_title": "Service Desk Analyst", "area": "Brisbane QLD", "region": "Australia"}
    jobs.write_text("\n".join(map(json.dumps, [high, low])), encoding="utf-8")
    high_a = rank.refresh_existing_analysis({"modele": "lfm3:1.7b", "points_forts": [], "points_a_verifier": []}, high, "AWS Terraform Linux Kubernetes Docker 2 years experience", "AWS Terraform Linux Kubernetes Docker")
    low_a = rank.refresh_existing_analysis({"modele": "lfm3:1.7b", "points_forts": [], "points_a_verifier": []}, low, "Microsoft 365 Intune", "AWS")
    report.with_suffix(".json").write_text(json.dumps({"analyses": [
        {"offre": high, "analyse": high_a, "description": "AWS Terraform Linux Kubernetes Docker 2 years experience"},
        {"offre": low, "analyse": low_a, "description": "Microsoft 365 Intune"},
    ], "echecs": []}), encoding="utf-8")
    upgraded = {**high_a, "modele": "qwen3:14b", "points_forts": ["Stack AWS/Terraform confirmée"]}
    with patch("sys.argv", ["local_rank", str(jobs), str(report), "--resume", "--refresh-ai", "--min-score", "70", "--model", "qwen3:14b"]), \
         patch.object(rank, "ollama_available", return_value=True), \
         patch.object(rank.fetcher, "fetch_job_detail") as fetch, \
         patch.object(rank, "analyze", return_value=upgraded) as model:
        rank.main()
    fetch.assert_not_called()
    model.assert_called_once()
    assert model.call_args.args[0]["job_id"] == "30"
    data = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
    by_id = {row["offre"]["job_id"]: row["analyse"] for row in data["analyses"]}
    assert by_id["30"]["modele"] == "qwen3:14b"
    assert by_id["31"]["modele"] == "lfm3:1.7b"


def test_off_target_domains_are_excluded_and_employers_are_tagged():
    import job_filters
    for title in (
        "System Engineer (Electrical/Instrumentation & Control)",
        "Graduate Control Systems Engineer",
        "Systems Engineer - CCTV & FRT",
        "z/OS Systems Engineer - CICS/MQ (NV1)",
    ):
        assert not job_filters.is_target_role({"job_title": title}), title
    for title in ("AWS Cloud Engineer", "Linux Infrastructure Engineer", "Site Reliability Engineer", "IT Support Engineer"):
        assert job_filters.is_target_role({"job_title": title}), title
    assert job_filters.employer_tag({"business_name": "Talenza"}) == "agency"
    assert job_filters.employer_tag({"business_name": "Green Light PS Pty Ltd"}) == "agency"
    assert job_filters.employer_tag({"business_name": "AC3 Pty Limited"}) == "aws_msp"
    assert job_filters.employer_tag({"business_name": "Versent"}) == "aws_msp"
    assert job_filters.employer_tag({"business_name": "Bureau Of Meteorology"}) == "public_sector"
    assert job_filters.employer_tag({"business_name": "NSW Department of Customer Service"}) == "public_sector"
    assert job_filters.employer_tag({"business_name": "Myconnect"}) == ""


def test_indeed_search_normalizes_and_deduplicates_against_seek(tmp_path):
    ind_spec = importlib.util.spec_from_file_location("indeed_search", Path(__file__).resolve().parents[1] / "indeed_search.py")
    ind = importlib.util.module_from_spec(ind_spec)
    ind_spec.loader.exec_module(ind)

    row = ind.normalize_row({
        "id": "abc123", "title": "Cloud Engineer", "company": "Teradata",
        "location": "Sydney, NSW, Australia", "job_type": "contract",
        "currency": "AUD", "min_amount": 900, "max_amount": 1000, "interval": "daily",
        "date_posted": "2026-11-25", "job_url": "https://au.indeed.com/viewjob?jk=abc123",
        "description": "AWS Terraform Linux 2 years experience",
    }, "Cloud Engineer")
    assert row["job_id"] == "in-abc123" and row["source"] == "indeed"
    assert row["work_type"] == "Contract/Temp"
    assert "AUD 900 - 1,000" in row["pay_range"]

    output, staged = tmp_path / "jobs.jsonl", tmp_path / "staged.jsonl"
    output.write_text(json.dumps({"job_id": "96069657", "job_title": "Cloud Operations Engineer", "business_name": "Are Media"}) + "\n", encoding="utf-8")
    dup = ind.normalize_row({
        "id": "in-dup", "title": "Cloud Operations Engineer", "company": "ARE MEDIA",
        "location": "Sydney", "job_url": "https://au.indeed.com/viewjob?jk=dup", "description": "AWS",
    }, "Cloud Operations Engineer")
    staged.write_text("\n".join(map(json.dumps, [dup, row])) + "\n", encoding="utf-8")
    added = ind.publish_feed(staged, output, merge=True)
    assert added == ["in-abc123"]


def test_local_rank_uses_inline_description_for_indeed_without_seek_fetch(tmp_path):
    jobs, report = tmp_path / "jobs.jsonl", tmp_path / "report.md"
    job = {
        "job_id": "in-999", "source": "indeed", "job_title": "Cloud Engineer",
        "business_name": "Teradata", "area": "Sydney NSW", "region": "Australia",
        "url": "https://au.indeed.com/viewjob?jk=999",
        "description": "2 years experience with AWS, Terraform and Linux.",
    }
    jobs.write_text(json.dumps(job), encoding="utf-8")
    expected = rank.refresh_existing_analysis({"modele": rank.DEFAULT_MODEL, "points_forts": ["AWS"], "points_a_verifier": []}, job, job["description"], "")
    with patch("sys.argv", ["local_rank", str(jobs), str(report), "--resume"]), \
         patch.object(rank.fetcher, "fetch_job_detail") as fetch, \
         patch.object(rank, "analyze", return_value=expected) as model:
        rank.main()
    fetch.assert_not_called()
    model.assert_called_once()
    data = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
    assert "description" not in data["analyses"][0]["offre"]
    assert "AWS" in data["analyses"][0]["description"]


def test_normalized_dedup_key_strips_company_suffixes_and_title_qualifiers():
    assert job_filters.normalized_dedup_key("Cloud Engineer", "AC3") == job_filters.normalized_dedup_key("Cloud Engineer", "AC3 Pty Limited")
    assert job_filters.normalized_dedup_key("Cloud Engineer - Hybrid", "iSelect Ltd") == job_filters.normalized_dedup_key("Cloud Engineer", "iSelect")
    assert job_filters.normalized_dedup_key("Systems Engineer", "Leidos Defence Australia") == job_filters.normalized_dedup_key("Systems Engineer", "Leidos")
    assert job_filters.normalized_dedup_key("DevOps Engineer (Sydney)", "Versent Group Pty Ltd") == job_filters.normalized_dedup_key("DevOps Engineer", "Versent")


def test_contract_duration_work_mode_and_recruiter_contacts():
    short = job_filters.contract_duration("Initial 6 months contract with possible extension.")
    assert short["months_min"] == 6 and short["months_max"] == 6 and short["whv_fit"] == "ideal"
    long_c = job_filters.contract_duration("12 month fixed-term contract based in Sydney.")
    assert long_c["months_min"] == 12 and long_c["whv_fit"] == "long"
    assert job_filters.contract_duration("We offer 16 weeks paid parental leave.")["whv_fit"] == "unknown"

    assert job_filters.work_mode("This is a 100% remote role across Australia.") == "remote"
    assert job_filters.work_mode("Flexible hybrid working arrangement, 2 days in office.") == "hybrid"
    assert job_filters.work_mode("This is a full-time on-site role in our Sydney office.") == "onsite"
    assert job_filters.work_mode("Manage hybrid cloud infrastructure on AWS.") == ""

    contacts = job_filters.recruiter_contacts(
        "Contact jane.doe@talenza.com.au or call 0412 345 678 (no-reply@seek.com.au ignored)."
    )
    assert contacts["emails"] == ["jane.doe@talenza.com.au"]
    assert contacts["phones"] == ["0412 345 678"]


def test_role_patterns_recover_target_titles_and_reject_off_target():
    for title in (
        "Linux Engineer",
        "Data Centre Technician",
        "Helpdesk Support Analyst",
        "Level 2 & 3 - Support",
        "Platforms Engineer",
        "AI & Automation Engineer",
    ):
        assert job_filters.is_target_role({"job_title": title}), title
    for title in (
        "Adobe Experience Platform Engineer",
        "Graduate Cloud Engineer - 2027 Start",
    ):
        assert not job_filters.is_target_role({"job_title": title}), title
    assert job_filters.is_senior({"job_title": "EL1 DevOps Engineer"})
    assert job_filters.is_senior({"job_title": "Cloud Architect"})
    assert not job_filters.is_senior({"job_title": "Junior Cloud Architect"})


def test_extract_evidence_prioritizes_work_rights_ignores_eeo_and_matches_clearances():
    iselect = "Applicants must hold unlimited Australian working rights only. Sponsorship is not available."
    assert "unlimited Australian working rights" in rank.extract_evidence(iselect, rank.VISA_TERMS)
    assert rank.extract_evidence("Hiring decisions are never based on race, religion, or citizenship.", rank.VISA_TERMS) is None
    assert rank.extract_evidence("The company may obtain nationality or citizenship information for export control.", rank.VISA_TERMS) is None
    for text in ("DISP clearance required.", "Must hold AusCheck.", "Negative Vetting 1 required.", "NV-1 clearance mandatory."):
        assert rank.extract_evidence(text, rank.CLEARANCE_TERMS), text


def test_unsafe_model_terms_blocks_clearance_paris_and_sanitizes_notes():
    result = rank.attach_source_evidence({
        "resume": "Habilitation sécurité nationale requise",
        "points_forts": [
            "Expérience basée à Paris et Bois-Colombes",
            "Bonne maîtrise AWS\net Terraform " + "x" * 300,
        ],
        "points_a_verifier": [
            "Exige sécurité nationale",
            "Prévoir un déménagement depuis Paris",
            "Connaissance Kubernetes",
        ],
    }, "Initial 6 months contract. Hybrid role. Contact tech@acme.com.au")
    assert "sécurité nationale" not in result["resume"]
    assert len(result["points_forts"]) == 1
    assert "\n" not in result["points_forts"][0] and len(result["points_forts"][0]) == 280
    assert result["points_a_verifier"] == ["Connaissance Kubernetes"]
    assert result["contract_duration"]["whv_fit"] == "ideal"
    assert result["work_mode"] == "hybrid"
    assert result["recruiter_contacts"]["emails"] == ["tech@acme.com.au"]


def test_terminal_failure_not_retried_and_prune_orphans_cleans_archive(tmp_path):
    jobs, report = tmp_path / "jobs.jsonl", tmp_path / "report.md"
    live_job = {"job_id": "1", "job_title": "Cloud Engineer"}
    expired_job = {"job_id": "2", "job_title": "DevOps Engineer"}
    jobs.write_text("\n".join(map(json.dumps, [live_job, expired_job])), encoding="utf-8")
    existing_live = {
        "offre": live_job,
        "analyse": rank.refresh_existing_analysis({"modele": rank.DEFAULT_MODEL, "points_forts": [], "points_a_verifier": []}, live_job, "AWS Terraform Linux", ""),
        "description": "AWS Terraform Linux",
    }
    orphan = {
        "offre": {"job_id": "999", "job_title": "Adobe Experience Platform Engineer"},
        "analyse": existing_live["analyse"],
        "description": "Legacy off-target row",
    }
    stale_exclusion = {"job": {"job_id": "1"}, "reason": "We have over 15 years of industry experience."}
    report.with_suffix(".json").write_text(json.dumps({
        "analyses": [existing_live, orphan],
        "echecs": [],
        "exclusions": [stale_exclusion],
    }), encoding="utf-8")

    with patch("sys.argv", ["local_rank", str(jobs), str(report), "--resume", "--prune-orphans"]), \
         patch.object(rank.fetcher, "fetch_job_detail", return_value=(None, None, "not_found")) as fetch, \
         patch.object(rank, "ollama_available", return_value=False), \
         patch.object(rank.time, "sleep"):
        rank.main()
        rank.main()

    fetch.assert_called_once_with("2", session=ANY)
    data = json.loads(report.with_suffix(".json").read_text(encoding="utf-8"))
    assert [row["offre"]["job_id"] for row in data["analyses"]] == ["1"]
    assert data["exclusions"] == []
    assert len(data["echecs"]) == 1 and data["echecs"][0]["job"]["job_id"] == "2" and data["echecs"][0]["terminal"] is True


def test_indeed_search_validates_url_and_cleans_markdown():
    ind_spec = importlib.util.spec_from_file_location("indeed_search", Path(__file__).resolve().parents[1] / "indeed_search.py")
    ind = importlib.util.module_from_spec(ind_spec)
    ind_spec.loader.exec_module(ind)

    for bad_url in (
        "http://au.indeed.com/viewjob?jk=1",
        "https://evil.com/viewjob?jk=1",
        "https://au.indeed.com.evil.com/viewjob?jk=1",
        "https://user:pass@au.indeed.com/viewjob?jk=1",
        "https://au.indeed.com:8443/viewjob?jk=1",
    ):
        assert ind.normalize_row({"id": "1", "title": "Cloud Engineer", "job_url": bad_url}, "Cloud") is None, bad_url

    row = ind.normalize_row({
        "id": "abc", "title": "Cloud Engineer", "company": "AC3 Pty Limited",
        "job_url": "https://au.indeed.com/viewjob?jk=abc",
        "description": "### **About**\n* **AWS** and __Terraform__***",
    }, "Cloud")
    assert row is not None
    assert "**" not in row["description"] and "__" not in row["description"] and "###" not in row["description"]
    assert "AWS and Terraform" in row["description"]


def test_render_escapes_markdown_and_blocks_non_https_urls(tmp_path):
    report = tmp_path / "report.md"
    analysis = rank.refresh_existing_analysis({"points_forts": ["AWS\nLinux"], "points_a_verifier": []}, {"job_title": "Cloud [AU] (AWS)"}, "AWS", "AWS")
    rank.render([{
        "offre": {
            "job_id": "1", "job_title": "Cloud [AU] (AWS)\nEngineer",
            "business_name": "Acme (Pty)", "area": "Sydney [NSW]",
            "url": "javascript:alert(1)",
        },
        "analyse": analysis,
    }], report)
    md = report.read_text(encoding="utf-8")
    assert r"Cloud \[AU\] \(AWS\) Engineer" in md
    assert r"Acme \(Pty\) — Sydney \[NSW\]" in md
    assert "javascript:" not in md
    assert "AWS Linux" in md

