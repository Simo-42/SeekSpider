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
    assert state["progress"]["status"] == "stopped"
