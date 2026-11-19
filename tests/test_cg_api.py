from types import SimpleNamespace

import pytest

from scripts import cg_api
from scripts.autotest import RubricRow


class Resp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data if data is not None else {}
        self.text = str(self._data)

    def json(self):
        return self._data


class FakeHttp:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def _do(self, method, url, json=None, **kw):
        self.calls.append((method, url, json))
        queue = self.responses.get((method, url))
        if queue:
            return queue.pop(0)
        return Resp(200, {})

    def get(self, url, **kw):
        return self._do("GET", url, **kw)

    def put(self, url, json=None, **kw):
        return self._do("PUT", url, json)

    def patch(self, url, json=None, **kw):
        return self._do("PATCH", url, json)

    def post(self, url, json=None, **kw):
        return self._do("POST", url, json)


def existing_row(id_, header, points=10):
    item = lambda i, h, p: SimpleNamespace(id=i, header=h, description="", points=p)
    return SimpleNamespace(
        id=id_, header=header, description="d", type="continuous", items=[item(id_ * 10, "Min", 0), item(id_ * 10 + 1, "Max", points)]
    )


class FakeAssignment:
    def __init__(self, rubric):
        self.rubric = rubric
        self.put_bodies = []
        self.uploads = []

    def get_rubric(self, *, assignment_id):
        return self.rubric

    def put_rubric(self, json_body, *, assignment_id):
        self.put_bodies.append(json_body)
        out = []
        next_id = 100
        for row in json_body["rows"]:
            rid = row.get("id")
            if rid is None:
                rid = next_id
                next_id += 1
            out.append(SimpleNamespace(id=rid, header=row["header"]))
        return out

    def upload_submission(self, multipart_data, *, assignment_id, is_test_submission=False):
        self.uploads.append((multipart_data, is_test_submission))


def client_with(rubric=None, responses=None):
    return SimpleNamespace(http=FakeHttp(responses), assignment=FakeAssignment(rubric or []))


def test_ensure_rubric_keeps_existing_and_adds_missing():
    client = client_with([existing_row(5, "Task 1"), existing_row(6, "Manual")])
    ids = cg_api.ensure_rubric(client, 1, [RubricRow("Task 1", "", 10), RubricRow("Task 2", "", 10)])
    sent = client.assignment.put_bodies[0]["rows"]
    assert [r["header"] for r in sent] == ["Task 1", "Manual", "Task 2"]
    assert [r.get("id") for r in sent[:2]] == [5, 6]
    assert sent[2]["type"] == "continuous"
    assert [i["points"] for i in sent[2]["items"]] == [0, 10]
    assert ids == {"Task 1": 5, "Task 2": 100}


def test_ensure_rubric_rerun_no_duplicates():
    client = client_with([existing_row(5, "Task 1")])
    ids = cg_api.ensure_rubric(client, 1, [RubricRow("Task 1", "", 10)])
    sent = client.assignment.put_bodies[0]["rows"]
    assert len(sent) == 1 and sent[0]["id"] == 5
    assert sent[0]["items"][1]["id"] == 51
    assert ids == {"Task 1": 5}


def test_push_sends_put_setup_test():
    client = client_with()
    config = {"setup": {"metadata": {"baseImageId": "x"}, "steps": []}, "test": {"steps": []}}
    cg_api.push_autotest(client, 7, config)
    methods = [(m, u) for m, u, _ in client.http.calls]
    assert methods == [("PUT", "/api/v2/autotest/7"), ("PATCH", "/api/v2/autotest/7"), ("PATCH", "/api/v2/autotest/7")]
    assert client.http.calls[1][2]["publishedSnapshot"] == {"unpublished": {}}
    assert "updatedTest" in client.http.calls[2][2]


def test_push_retries_setup_without_metadata():
    url = "/api/v2/autotest/7"
    client = client_with(responses={("PATCH", url): [Resp(400, {"message": "metadata"})]})
    config = {"setup": {"metadata": {"baseImageId": "x"}, "steps": []}, "test": {"steps": []}}
    cg_api.push_autotest(client, 7, config)
    patches = [body for m, u, body in client.http.calls if m == "PATCH"]
    assert "metadata" in patches[0]["updatedSetup"]
    assert "metadata" not in patches[1]["updatedSetup"]
    assert "updatedTest" in patches[2]


def test_push_raises_on_error():
    url = "/api/v2/autotest/7"
    client = client_with(responses={("PUT", url): [Resp(403, {"message": "nope"})]})
    with pytest.raises(cg_api.ApiError):
        cg_api.push_autotest(client, 7, {"setup": {"steps": []}, "test": {"steps": []}})


def test_create_snapshot_returns_id():
    url = "/api/v2/autotest/7/snapshots/"
    client = client_with(responses={("POST", url): [Resp(200, {"snapshot": {"snapshotId": "abc"}})]})
    assert cg_api.create_snapshot(client, 7) == "abc"


def test_publish_retries_until_accepted():
    url = "/api/v2/autotest/7"
    client = client_with(responses={("PATCH", url): [Resp(400), Resp(409)]})
    sleeps = []
    cg_api.publish_snapshot(client, 7, "abc", wait_s=60, sleep=sleeps.append)
    bodies = [b for m, u, b in client.http.calls if m == "PATCH"]
    assert len(bodies) == 3
    assert bodies[-1] == {"publishedSnapshot": {"published": "abc"}}
    assert sleeps == [10, 10]


def test_publish_gives_up():
    url = "/api/v2/autotest/7"
    client = client_with(responses={("PATCH", url): [Resp(400)] * 10})
    with pytest.raises(cg_api.ApiError):
        cg_api.publish_snapshot(client, 7, "abc", wait_s=20, sleep=lambda s: None)


def test_upload_skipped_when_empty():
    client = client_with()
    cg_api.upload_test_submission(client, 7, [])
    assert client.assignment.uploads == []
    cg_api.upload_test_submission(client, 7, [("hw.ipynb", b"{}")])
    assert client.assignment.uploads[0][1] is True


def test_create_snapshot_unexpected_shape():
    url = "/api/v2/autotest/7/snapshots/"
    client = client_with(responses={("POST", url): [Resp(200, {"weird": 1})]})
    with pytest.raises(cg_api.ApiError) as e:
        cg_api.create_snapshot(client, 7)
    assert "weird" in str(e.value)


@pytest.mark.parametrize("status", [401, 403, 404])
def test_publish_stops_on_auth_errors(status):
    url = "/api/v2/autotest/7"
    client = client_with(responses={("PATCH", url): [Resp(status)]})
    sleeps = []
    with pytest.raises(cg_api.ApiError):
        cg_api.publish_snapshot(client, 7, "abc", wait_s=600, sleep=sleeps.append)
    assert sleeps == []


def test_ensure_rubric_warns_about_unconnected_and_points():
    client = client_with([existing_row(5, "Task 1", points=5), existing_row(6, "Old task")])
    warnings = []
    cg_api.ensure_rubric(client, 1, [RubricRow("Task 1", "", 10)], warnings=warnings)
    text = " ".join(warnings)
    assert "Old task" in text
    assert "Task 1" in text and "5" in text
