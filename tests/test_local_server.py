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
    state = server.state(jobs, report, 3, '')
    assert [job['job_id'] for job in state['jobs']] == ['1']
    assert state['progress']['excluded'] == 2
    assert state['progress']['completed'] == state['progress']['total'] == 1
