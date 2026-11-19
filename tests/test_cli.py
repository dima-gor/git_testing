from pathlib import Path

import pytest

from scripts import cg_api, push_assignment

FIXTURES = Path(__file__).parent / "fixtures"


class Recorder:
    def __init__(self):
        self.calls = []

    def fn(self, name, result=None):
        def f(*args, **kwargs):
            self.calls.append(name)
            return result
        return f


@pytest.fixture
def rec(monkeypatch):
    r = Recorder()
    client = type("C", (), {"http": None, "__enter__": lambda self: self, "__exit__": lambda self, *e: None})()
    monkeypatch.setattr(cg_api, "login", r.fn("login", client))
    monkeypatch.setattr(cg_api, "create_assignment", r.fn("create_assignment", 77))
    monkeypatch.setattr(cg_api, "course_of", r.fn("course_of", 5))
    monkeypatch.setattr(cg_api, "set_editor_only", r.fn("set_editor_only", []))
    monkeypatch.setattr(cg_api, "ensure_rubric", lambda c, a, rows, warnings=None: (r.calls.append("ensure_rubric"), {x.header: i for i, x in enumerate(rows)})[1])
    monkeypatch.setattr(cg_api, "push_autotest", r.fn("push_autotest"))
    monkeypatch.setattr(cg_api, "upload_test_submission", r.fn("upload_test_submission"))
    monkeypatch.setattr(cg_api, "create_snapshot", r.fn("create_snapshot", "snap1"))
    monkeypatch.setattr(cg_api, "publish_snapshot", r.fn("publish_snapshot"))
    monkeypatch.setattr(cg_api, "set_description", r.fn("set_description"))
    monkeypatch.setattr(push_assignment, "host_of", lambda client: "https://example.test")
    return r


def test_dry_run_writes_json_and_no_login(rec, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code = push_assignment.main(["--source", str(FIXTURES / "quiz_min"), "--type", "quiz", "--dry-run"])
    assert code == 0
    assert (tmp_path / "build" / "quiz_min.autotest.json").is_file()
    assert (tmp_path / "build" / "quiz_min.rubric.json").is_file()
    assert "login" not in rec.calls


def test_missing_files_exit_2_no_login(rec, tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    code = push_assignment.main(["--source", str(empty), "--type", "quiz", "--course", "1"])
    assert code == 2
    assert "quiz.md" in capsys.readouterr().err
    assert rec.calls == []


@pytest.mark.parametrize("publish", [True, False])
def test_publish_flag(rec, publish):
    args = ["--source", str(FIXTURES / "jupyter_min"), "--type", "jupyter", "--course", "5"]
    if publish:
        args.append("--publish")
    assert push_assignment.main(args) == 0
    assert rec.calls.count("publish_snapshot") == (1 if publish else 0)
    assert rec.calls[:4] == ["login", "create_assignment", "upload_test_submission", "set_editor_only"]
    assert "create_snapshot" in rec.calls


def test_existing_assignment_needs_confirmation(rec, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    code = push_assignment.main(["--source", str(FIXTURES / "quiz_min"), "--type", "quiz", "--assignment", "9"])
    assert code == 1
    assert "push_autotest" not in rec.calls
    assert "create_assignment" not in rec.calls


def test_existing_assignment_with_yes(rec):
    code = push_assignment.main(["--source", str(FIXTURES / "quiz_min"), "--type", "quiz", "--assignment", "9", "--yes"])
    assert code == 0
    assert "create_assignment" not in rec.calls
    assert "push_autotest" in rec.calls


def test_source_requires_type(rec, capsys):
    with pytest.raises(SystemExit):
        push_assignment.main(["--source", str(FIXTURES / "quiz_min"), "--dry-run"])


def test_menu_picks_example(rec, monkeypatch, tmp_path):
    monkeypatch.setattr("builtins.input", lambda prompt="": "2")
    monkeypatch.setattr(push_assignment, "EXAMPLES", {"jupyter": FIXTURES / "jupyter_min", "quiz": FIXTURES / "quiz_min"})
    monkeypatch.chdir(tmp_path)
    assert push_assignment.main(["--dry-run"]) == 0
    assert (tmp_path / "build" / "quiz_min.autotest.json").is_file()


def test_library_error_exits_3(rec, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("403 Forbidden")
    monkeypatch.setattr(cg_api, "create_assignment", boom)
    code = push_assignment.main(["--source", str(FIXTURES / "quiz_min"), "--type", "quiz", "--course", "1"])
    assert code == 3
    assert "403 Forbidden" in capsys.readouterr().err


def test_test_submission_uploaded_before_editor_only(rec):
    push_assignment.main(["--source", str(FIXTURES / "jupyter_min"), "--type", "jupyter", "--course", "5"])
    assert rec.calls.index("upload_test_submission") < rec.calls.index("set_editor_only")


def test_client_session_opened_once_for_whole_run(rec, monkeypatch):
    """codegrade's client must be entered once; raw client.http calls between
    library calls otherwise re-open httpx ('Cannot open a client instance more than once')."""
    events = []

    class Client:
        http = None

        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, *exc):
            events.append("exit")

    monkeypatch.setattr(cg_api, "login", lambda: Client())
    code = push_assignment.main(["--source", str(FIXTURES / "quiz_min"), "--type", "quiz", "--course", "1"])
    assert code == 0
    assert events == ["enter", "exit"]



def test_recreate_flag_passed(rec, monkeypatch):
    seen = {}
    monkeypatch.setattr(cg_api, "push_autotest", lambda c, a, cfg, recreate=False: seen.setdefault("recreate", recreate))
    push_assignment.main(["--source", str(FIXTURES / "quiz_min"), "--type", "quiz", "--assignment", "9", "--yes", "--recreate"])
    assert seen["recreate"] is True


def test_description_uploaded_when_present(rec, tmp_path):
    import shutil
    folder = tmp_path / "q"
    shutil.copytree(FIXTURES / "quiz_min", folder)
    (folder / "description.md").write_text("intro")
    assert push_assignment.main(["--source", str(folder), "--type", "quiz", "--course", "1"]) == 0
    assert "set_description" in rec.calls


def test_no_description_not_uploaded(rec):
    assert push_assignment.main(["--source", str(FIXTURES / "quiz_min"), "--type", "quiz", "--course", "1"]) == 0
    assert "set_description" not in rec.calls


def test_points_must_be_positive(rec):
    with pytest.raises(SystemExit):
        push_assignment.main(["--example", "quiz", "--dry-run", "--points", "0"])


def test_non_numeric_course_prompt(rec, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": "abc")
    code = push_assignment.main(["--source", str(FIXTURES / "quiz_min"), "--type", "quiz"])
    assert code == 2
    assert "course id" in capsys.readouterr().err.lower()
    assert "login" not in rec.calls
