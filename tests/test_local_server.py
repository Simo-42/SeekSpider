import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("local_server", Path(__file__).resolve().parents[1] / "local_server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def test_state_shows_live_analyses_without_duplicates(tmp_path):
    jobs = tmp_path / "jobs.jsonl"
    jobs.write_text('\n'.join([json.dumps({"job_id": "12", "job_title": "Cloud"})] * 2 + [json.dumps({"job_id": "13", "job_title": "Senior Cloud Engineer"})]), encoding="utf-8")
    report = tmp_path / "analysis.md"
    report.write_text("## 82/100 — Cloud\n\n[Employer — Sydney](https://www.seek.com.au/job/12)\n\nPertinent.\n\n**Points forts :** AWS; Linux\n\n**À vérifier :** Visa\n\n**Expérience :** non précisé\n\n**Visa / sponsoring :** non précisé\n", encoding="utf-8")
    report.with_suffix('.json').write_text(json.dumps({"analyses": [{"offre": {"job_id": "12"}, "analyse": {
        "score": 82, "score_method": server.SCORE_VERSION, "resume": "Pertinent.",
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
    data = {'analyses': [{'offre': {'job_id': '1'}, 'analyse': {'score': 45, 'score_method': server.SCORE_VERSION}}],
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
