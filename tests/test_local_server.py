import http.client
import importlib.util
import json
import threading
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("local_server", Path(__file__).resolve().parents[1] / "local_server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def test_state_shows_live_analyses_without_duplicates(tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    jobs.write_text('\n'.join([json.dumps({"job_id": "12", "job_title": "Cloud"})] * 2 + [json.dumps({"job_id": "13", "job_title": "Senior Cloud Engineer"})]), encoding="utf-8")
    report = tmp_path / "analysis.md"
    report.write_text("## 82/100 — Cloud\n\n[Employer — Sydney](https://www.seek.com.au/job/12)\n\nPertinent.\n\n**Points forts :** AWS; Linux\n\n**À vérifier :** Visa\n\n**Expérience :** non précisé\n\n**Visa / sponsoring :** non précisé\n", encoding="utf-8")
    report.with_suffix('.json').write_text(json.dumps({"analyses": [{"offre": {"job_id": "12"}, "analyse": {
        "score": 82, "score_method": server.SCORE_VERSION, "profile_fingerprint": server.profile_fingerprint(""), "resume": "Pertinent.",
        "points_forts": ["AWS", "Linux"], "points_a_verifier": ["Visa"]}}]}), encoding="utf-8")
    state = server.state(jobs, report, 20, "")
    assert len(state["jobs"]) == 1
    assert state["analyses"]["12"]["score"] == 82
    assert state["analyses"]["12"]["points_forts"] == ["AWS", "Linux"]
    assert state["progress"]["completed"] == 1
    assert state["progress"]["excluded"] == 1
    assert state["progress"]["status"] == "finished"


def test_state_hides_past_and_new_five_year_exclusions(tmp_path):
    jobs, report = tmp_path / 'jobs.jsonl', tmp_path / 'report.md'
    jobs.write_text('\n'.join(json.dumps({'job_id': str(i), 'job_title': 'Cloud Engineer'}) for i in range(3)), encoding='utf-8')
    data = {'analyses': [{'offre': {'job_id': '0'}, 'analyse': {'score': 70, 'preuve_experience': 'Skills & Experience 5+ years’ experience in DevOps.'}},
                         {'offre': {'job_id': '1'}, 'analyse': {'score': 75, 'preuve_experience': '3-5 years of experience.'}}],
            'exclusions': [{'job': {'job_id': '2'}, 'reason': 'At least 5 years of experience.'}]}
    report.with_suffix('.json').write_text(json.dumps(data), encoding='utf-8')
    report.write_text('Rapport en cours de mise à jour.', encoding='utf-8')
    state = server.state(jobs, report, 3, '')
    assert [job['job_id'] for job in state['jobs']] == ['1']
    assert state['progress']['excluded'] == 2
    assert state['progress']['completed'] == 0 and state['progress']['total'] == 1
    assert state['progress']['stale'] == 1


def test_state_hides_misleading_evidence_from_older_results(tmp_path):
    jobs, report = tmp_path / 'jobs.jsonl', tmp_path / 'report.md'
    jobs.write_text(json.dumps({'job_id': '1', 'job_title': 'Cloud Engineer'}), encoding='utf-8')
    data = {'analyses': [{'offre': {'job_id': '1'}, 'analyse': {'score': 45,
        'preuve_experience': 'A business with more than 30 years of experience.',
        'preuve_visa': 'Equal opportunity regardless of race, colour, religion, citizenship, or age.'}}]}
    report.with_suffix('.json').write_text(json.dumps(data), encoding='utf-8')
    analysis = server.state(jobs, report, 1, '')['analyses']['1']
    assert 'Aucun extrait pertinent' in analysis['preuve_experience']
    assert 'Aucun extrait pertinent' in analysis['preuve_visa']
    assert analysis['score'] is None and analysis['score_obsolete']


def test_stale_failures_do_not_block_finished_status(tmp_path):
    jobs, report = tmp_path / 'jobs.jsonl', tmp_path / 'report.md'
    jobs.write_text(json.dumps({'job_id': '1', 'job_title': 'Cloud Engineer'}), encoding='utf-8')
    data = {'analyses': [{'offre': {'job_id': '1'}, 'analyse': {'score': 45, 'score_method': server.SCORE_VERSION, 'profile_fingerprint': server.profile_fingerprint('')}}],
            'echecs': [{'job': {'job_id': '999'}, 'status': 'not_found'}]}
    report.with_suffix('.json').write_text(json.dumps(data), encoding='utf-8')
    progress = server.state(jobs, report, 1, '')['progress']
    assert progress['status'] == 'finished' and progress['failed'] == 0


def test_state_hides_off_target_and_senior_titles(tmp_path):
    jobs, report = tmp_path / 'jobs.jsonl', tmp_path / 'analysis.md'
    jobs.write_text('\n'.join(json.dumps({'job_id': str(i), 'job_title': title})
                              for i, title in enumerate(('Cloud Engineer', 'Engineer Mining', 'Senior DevOps Engineer',
                                                         'AI Engineers & Engineering Leads', 'Operations Support Mgr / IT Support Analyst'))), encoding='utf-8')
    report.write_text('', encoding='utf-8')
    state = server.state(jobs, report, 3, '')
    assert [job['job_id'] for job in state['jobs']] == ['0']
    assert state['progress']['excluded'] == 4


def test_state_hides_legacy_model_score_and_offers_recalculation(tmp_path):
    jobs, report, profile = tmp_path / 'jobs.jsonl', tmp_path / 'analysis.md', tmp_path / 'profile.txt'
    jobs.write_text(json.dumps({'job_id': '1', 'job_title': 'Cloud Engineer'}), encoding='utf-8')
    report.write_text('', encoding='utf-8')
    report.with_suffix('.json').write_text(json.dumps({'analyses': [
        {'offre': {'job_id': '1'}, 'analyse': {'score': 85, 'resume': 'Old model result'}}]}), encoding='utf-8')
    profile.write_text('AWS Terraform Linux', encoding='utf-8')
    state = server.state(jobs, report, 1, '', profile)
    assert state['analyses']['1']['score'] is None
    assert state['progress']['stale'] == 1 and state['progress']['completed'] == 0
    assert state['progress']['can_start']


def test_show_professional_profile_and_hide_score_after_cv_changes(tmp_path):
    jobs, report, profile = (tmp_path / name for name in ("jobs.jsonl", "report.md", "profile.txt"))
    cv = "Private Name – hidden@example.com\nSKILLS\nCloud: AWS\nLanguages: French (native)\n"
    profile.write_text(cv, encoding="utf-8")
    jobs.write_text(json.dumps({"job_id": "1", "job_title": "Cloud Engineer"}), encoding="utf-8")
    report.with_suffix(".json").write_text(json.dumps({"analyses": [
        {"offre": {"job_id": "1"}, "analyse": {
            "score": 68, "score_method": server.SCORE_VERSION, "profile_fingerprint": server.profile_fingerprint(cv)}}
    ]}), encoding="utf-8")
    payload = server.state(jobs, report, 1, "", profile)
    assert payload["analyses"]["1"]["score"] == 68
    assert payload["profile"]["skills"] == ["AWS"]
    assert payload["profile"]["languages"] == ["French (native)"]
    assert "hidden@example.com" not in json.dumps(payload)
    assert "profile_fingerprint" not in json.dumps(payload)
    profile.write_text(cv.replace("AWS", "Terraform"), encoding="utf-8")
    updated = server.state(jobs, report, 1, "", profile)
    assert updated["profile"]["skills"] == ["Terraform"]
    assert updated["analyses"]["1"]["score"] is None
    assert updated["progress"]["stale"] == 1 and updated["progress"]["can_start"]


def test_search_progress_disables_analysis_and_reports_a_stopped_worker(tmp_path):
    jobs, report, profile = (tmp_path / name for name in ("jobs.jsonl", "report.md", "profile.txt"))
    jobs.write_text('{"job_id":"1","job_title":"Cloud Engineer"}\n', encoding="utf-8")
    profile.write_text("AWS", encoding="utf-8")
    jobs.with_suffix(".search.json").write_text(json.dumps({
        "status": "running", "completed": 12, "total": 42, "new_jobs": 0
    }), encoding="utf-8")
    with patch.object(server, "container_running", side_effect=lambda name: name == "search"):
        payload = server.state(jobs, report, 1, "analysis", profile, "search")
    assert payload["search"]["status"] == "running" and payload["search"]["completed"] == 12
    assert not payload["search"]["can_start"] and not payload["progress"]["can_start"]
    stopped = server.state(jobs, report, 1, "", profile)
    assert stopped["search"]["status"] == "failed"
    assert stopped["search"]["can_start"] and stopped["progress"]["can_start"]


def test_search_estimate_tracks_processed_pages_and_freezes_at_completion(tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    status = jobs.with_suffix(".search.json")
    snapshot = {
        "status": "running", "completed": 12, "total": 42, "new_jobs": 0,
        "started_at": 1000, "updated_at": 1060, "discovered_jobs": 150,
        "last_query": "SRE", "recent_new_jobs": [{"job_title": "SRE", "business_name": "Example", "area": "Perth"}],
    }
    status.write_text(json.dumps(snapshot))
    with patch.object(server.time, "time", return_value=1065):
        live = server.search_state(jobs, True, False)
    assert live["elapsed_seconds"] == 65 and live["remaining_seconds"] == 145
    assert live["discovered_jobs"] == 150 and live["recent_new_jobs"][0]["job_title"] == "SRE"
    with patch.object(server.time, "time", return_value=1250):
        stalled = server.search_state(jobs, True, False)
    assert stalled["elapsed_seconds"] == 250 and stalled["remaining_seconds"] is None
    status.write_text(json.dumps({**snapshot, "completed": 42, "status": "finished", "updated_at": 1215}))
    finished = server.search_state(jobs, False, False)
    assert finished["elapsed_seconds"] == 215 and finished["remaining_seconds"] is None


def test_legacy_search_previews_do_not_appear_as_new_ads(tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    jobs.with_suffix(".search.json").write_text(json.dumps({
        "status": "finished", "completed": 42, "total": 42, "new_jobs": 3,
        "seen_jobs": 100, "recent_jobs": [{"job_title": "Already known"}],
    }))
    state = server.search_state(jobs, False, False)
    assert state["new_jobs"] == 3 and state["discovered_jobs"] is None
    assert state["recent_new_jobs"] == []


def test_state_exposes_whv_flags_and_ignores_cleaned_legacy_eeo_quote(tmp_path):
    jobs, report = tmp_path / "jobs.jsonl", tmp_path / "report.md"
    jobs.write_text("\n".join(json.dumps({"job_id": str(i), "job_title": "Cloud Engineer"}) for i in range(1, 5)), encoding="utf-8")
    data = {"analyses": [
        {"offre": {"job_id": "1"}, "analyse": {
            "preuve_habilitation": "Must hold an NV1 security clearance.",
            "preuve_visa": "Aucun extrait repéré"}},
        {"offre": {"job_id": "2"}, "analyse": {
            "preuve_habilitation": "Aucun extrait repéré",
            "preuve_visa": "Applicants must be an Australian citizen or permanent resident."}},
        {"offre": {"job_id": "3"}, "analyse": {
            "preuve_habilitation": "Aucun extrait repéré",
            "preuve_visa": "Aucun extrait repéré"}},
        {"offre": {"job_id": "4"}, "analyse": {
            "preuve_visa": "Equal opportunity regardless of race, colour, religion, citizenship, or age."}},
    ]}
    report.with_suffix(".json").write_text(json.dumps(data), encoding="utf-8")
    analyses = server.state(jobs, report, 4, "")["analyses"]
    assert analyses["1"]["whv_flags"] == {"clearance": True, "citizen_pr_risk": False, "no_sponsorship": False, "visa_mention": False}
    assert analyses["2"]["whv_flags"] == {"clearance": False, "citizen_pr_risk": True, "no_sponsorship": False, "visa_mention": True}
    assert analyses["3"]["whv_flags"] == {"clearance": False, "citizen_pr_risk": False, "no_sponsorship": False, "visa_mention": False}
    assert analyses["4"]["whv_flags"] == {"clearance": False, "citizen_pr_risk": False, "no_sponsorship": False, "visa_mention": False}


def test_triage_persistence_validation_and_state_filtering(tmp_path):
    jobs, report = tmp_path / "jobs.jsonl", tmp_path / "nested" / "report.md"
    jobs.write_text("\n".join([
        json.dumps({"job_id": "10", "job_title": "Cloud Engineer"}),
        json.dumps({"job_id": "11", "job_title": "DevOps Engineer"}),
        json.dumps({"job_id": "12", "job_title": "Senior Cloud Engineer"}),
    ]), encoding="utf-8")

    shortlist = server.save_triage_entry(report, "10", "shortlist", "  Bon fit AWS  ")
    applied = server.save_triage_entry(report, "11", "applied", "Candidature envoyée")
    dismissed = server.save_triage_entry(report, "12", "dismissed", "Trop senior")
    assert shortlist["status"] == "shortlist" and shortlist["note"] == "Bon fit AWS"
    assert isinstance(shortlist["updated_at"], (int, float))
    assert applied["status"] == "applied" and dismissed["status"] == "dismissed"

    saved = server.read_triage(report)
    assert set(saved) == {"10", "11", "12"}
    assert saved["10"]["note"] == "Bon fit AWS"

    payload = server.state(jobs, report, 3, "")
    assert set(payload["triage"]) == {"10", "11"}
    assert payload["triage"]["10"]["status"] == "shortlist"

    for args in (
        ("", "shortlist", ""),
        ("   ", "shortlist", ""),
        (10, "shortlist", ""),
        ("10", "invalid", ""),
        ("10", "shortlist", "x" * 501),
        ("10", "shortlist", 42),
    ):
        try:
            server.save_triage_entry(report, *args)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for {args!r}")

    assert server.save_triage_entry(report, "11", "todo", "   ") is None
    assert "11" not in server.read_triage(report)
    assert set(server.state(jobs, report, 3, "")["triage"]) == {"10"}


def test_state_tags_employers_and_excludes_non_it_domains(tmp_path):
    jobs, report = tmp_path / "jobs.jsonl", tmp_path / "report.md"
    jobs.write_text("\n".join(map(json.dumps, [
        {"job_id": "1", "job_title": "Cloud Engineer", "business_name": "Talenza"},
        {"job_id": "2", "job_title": "Cloud Engineer", "business_name": "Versent"},
        {"job_id": "3", "job_title": "Application Support Developer", "business_name": "Bureau Of Meteorology"},
        {"job_id": "4", "job_title": "Systems Engineer - CCTV & FRT", "business_name": "Endeavour Group"},
    ])), encoding="utf-8")
    payload = server.state(jobs, report, 4, "")
    tags = {j["job_id"]: j["employer_tag"] for j in payload["jobs"]}
    assert tags == {"1": "agency", "2": "aws_msp", "3": "public_sector"}


def test_state_marks_source_and_strips_inline_description(tmp_path):
    jobs, report = tmp_path / "jobs.jsonl", tmp_path / "report.md"
    jobs.write_text("\n".join(map(json.dumps, [
        {"job_id": "100", "job_title": "Cloud Engineer", "business_name": "Talenza"},
        {"job_id": "in-abc", "source": "indeed", "job_title": "Cloud Engineer", "business_name": "Teradata", "description": "Long text"},
    ])), encoding="utf-8")
    payload = server.state(jobs, report, 2, "")
    by_id = {j["job_id"]: j for j in payload["jobs"]}
    assert by_id["100"]["source"] == "seek"
    assert by_id["in-abc"]["source"] == "indeed"
    assert "description" not in by_id["in-abc"]


def test_state_cross_source_dedup_prefers_seek_over_indeed(tmp_path):
    jobs, report = tmp_path / "jobs.jsonl", tmp_path / "report.md"
    jobs.write_text("\n".join(map(json.dumps, [
        {"job_id": "in-ac3", "source": "indeed", "job_title": "Cloud Engineer", "business_name": "AC3"},
        {"job_id": "9001", "job_title": "Cloud Engineer (Hybrid)", "business_name": "AC3 Pty Limited"},
    ])), encoding="utf-8")
    payload = server.state(jobs, report, 2, "")
    assert [j["job_id"] for j in payload["jobs"]] == ["9001"]
    assert payload["jobs"][0]["source"] == "seek"
    assert payload["progress"]["excluded"] == 1


def test_state_computes_metadata_from_cached_description_and_scrubs_leaks(tmp_path):
    jobs, report = tmp_path / "jobs.jsonl", tmp_path / "report.md"
    jobs.write_text(json.dumps({"job_id": "1", "job_title": "Cloud Engineer"}), encoding="utf-8")
    desc = (
        "Initial 6 month contract with hybrid working (2 days in office). "
        "Contact jane.doe@talenza.com.au or 0412 345 678."
    )
    data = {"analyses": [{"offre": {"job_id": "1"}, "description": desc, "analyse": {
        "score": 80, "score_method": server.SCORE_VERSION, "profile_fingerprint": server.profile_fingerprint(""),
        "points_forts": ["Expérience AWS solide", "Basé à Bois-Colombes près de Paris"],
        "points_a_verifier": ["Relocation à prévoir", "Expérience Azure"],
    }}]}
    report.with_suffix(".json").write_text(json.dumps(data), encoding="utf-8")
    analysis = server.state(jobs, report, 1, "")["analyses"]["1"]
    assert analysis["contract_duration"]["label"] == "6 mois"
    assert analysis["contract_duration"]["whv_fit"] == "ideal"
    assert analysis["work_mode"] == "hybrid"
    assert analysis["recruiter_contacts"] == {"emails": ["jane.doe@talenza.com.au"], "phones": ["0412 345 678"]}
    assert analysis["points_forts"] == ["Expérience AWS solide"]
    assert analysis["points_a_verifier"] == ["Expérience Azure"]


def test_terminal_failure_does_not_block_finished_and_false_exclusion_recovers(tmp_path):
    jobs, report = tmp_path / "jobs.jsonl", tmp_path / "report.md"
    jobs.write_text("\n".join(map(json.dumps, [
        {"job_id": "1", "job_title": "Cloud Engineer"},
        {"job_id": "2", "job_title": "DevOps Engineer"},
        {"job_id": "3", "job_title": "SRE"},
    ])), encoding="utf-8")
    fp = server.profile_fingerprint("")
    data = {
        "analyses": [
            {"offre": {"job_id": "1"}, "analyse": {"score": 80, "score_method": server.SCORE_VERSION, "profile_fingerprint": fp}},
            {"offre": {"job_id": "3"}, "analyse": {"score": 78, "score_method": server.SCORE_VERSION, "profile_fingerprint": fp}},
        ],
        "echecs": [{"job": {"job_id": "2"}, "status": "not_found", "terminal": True}],
        "exclusions": [{"job": {"job_id": "3"}, "reason": "Our company has over 15 years of experience."}],
    }
    report.with_suffix(".json").write_text(json.dumps(data), encoding="utf-8")
    payload = server.state(jobs, report, 3, "")
    assert {j["job_id"] for j in payload["jobs"]} == {"1", "2", "3"}
    assert payload["progress"]["failed"] == 0
    assert payload["progress"]["pending"] == 0
    assert payload["progress"]["status"] == "finished"


def test_ollama_retry_sets_ai_pending_and_keeps_can_start_true(tmp_path):
    jobs, report, profile = tmp_path / "jobs.jsonl", tmp_path / "report.md", tmp_path / "profile.txt"
    profile.write_text("AWS Terraform", encoding="utf-8")
    jobs.write_text(json.dumps({"job_id": "1", "job_title": "Cloud Engineer"}), encoding="utf-8")
    data = {"analyses": [{"offre": {"job_id": "1"}, "analyse": {
        "score": 81, "score_method": server.SCORE_VERSION,
        "profile_fingerprint": server.profile_fingerprint("AWS Terraform"),
        "modele": server.AI_UNAVAILABLE_MODEL,
    }}]}
    report.with_suffix(".json").write_text(json.dumps(data), encoding="utf-8")
    with patch.object(server, "container_running", side_effect=lambda name: name == "seekspider-ollama"):
        payload = server.state(jobs, report, 1, "ranking", profile)
    assert payload["analyses"]["1"]["ai_pending"] is True
    assert payload["progress"]["ai_pending"] == 1
    assert payload["progress"]["can_start"] is True
    assert payload["progress"]["status"] == "stopped"


def test_search_state_resets_stale_finished_progress_while_booting(tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    jobs.with_suffix(".search.json").write_text(json.dumps({
        "status": "finished", "completed": 42, "total": 42, "new_jobs": 7,
        "started_at": 1000, "updated_at": 1200, "discovered_jobs": 200,
        "recent_new_jobs": [{"job_title": "Old ad"}],
    }), encoding="utf-8")
    booting = server.search_state(jobs, running=True, analysing=False)
    assert booting["status"] == "running"
    assert booting["completed"] == 0 and booting["total"] == 0
    assert booting["recent_new_jobs"] == []
    assert booting["discovered_jobs"] is None
    assert booting["remaining_seconds"] is None
    assert booting["can_start"] is False


def test_live_server_health_security_headers_host_check_and_triage(tmp_path):
    jobs, report = tmp_path / "jobs.jsonl", tmp_path / "report.md"
    jobs.write_text(json.dumps({"job_id": "42", "job_title": "Cloud Engineer"}), encoding="utf-8")
    httpd = server.create_server(jobs, report, port=0)
    port = httpd.server_port
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/health", headers={"Host": f"127.0.0.1:{port}"})
        res = conn.getresponse()
        body = json.loads(res.read().decode("utf-8"))
        assert res.status == 200 and body == {"ok": True}
        assert res.getheader("X-Frame-Options") == "DENY"
        assert res.getheader("Content-Security-Policy") == "frame-ancestors 'none'"
        assert res.getheader("Referrer-Policy") == "no-referrer"
        assert res.getheader("Cache-Control") == "no-store"
        assert res.getheader("X-Content-Type-Options") == "nosniff"

        conn.request("GET", "/favicon.ico", headers={"Host": f"127.0.0.1:{port}"})
        fav = conn.getresponse()
        fav.read()
        assert fav.status == 204

        conn.request("GET", "/health", headers={"Host": f"evil.example:{port}"})
        bad = conn.getresponse()
        bad.read()
        assert bad.status == 403
        assert bad.getheader("X-Frame-Options") == "DENY"

        conn.close()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        payload = json.dumps({"job_id": "42", "status": "shortlist", "note": "Top AWS"}).encode("utf-8")
        conn.request("POST", "/api/triage", body=payload, headers={
            "Host": f"localhost:{port}",
            "Origin": f"http://localhost:{port}",
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
        })
        post = conn.getresponse()
        post_body = json.loads(post.read().decode("utf-8"))
        assert post.status == 200 and post_body["ok"] is True
        assert post_body["triage"]["status"] == "shortlist"
        assert post.getheader("X-Frame-Options") == "DENY"
        assert server.read_triage(report)["42"]["note"] == "Top AWS"

        too_long = json.dumps({"job_id": "x" * 129, "status": "shortlist", "note": ""}).encode("utf-8")
        conn.request("POST", "/api/triage", body=too_long, headers={
            "Host": f"localhost:{port}",
            "Origin": f"http://localhost:{port}",
            "Content-Type": "application/json",
            "Content-Length": str(len(too_long)),
        })
        bad_id = conn.getresponse()
        bad_id.read()
        assert bad_id.status == 400
        conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
