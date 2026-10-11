import base64

import pytest

import jenkins_common as jc
from conftest import FakeOpener, FakeResponse, http_error


def test_credentials_from_env_win_over_bashrc(tmp_path):
    rc = tmp_path / ".bashrc"
    rc.write_text("export JENKINS_USER=fromfile\nexport JENKINS_API_TOKEN=filetok\n")
    env = {"JENKINS_USER": "envuser", "JENKINS_API_TOKEN": "envtok"}
    assert jc.load_credentials(env, rc) == ("envuser", "envtok")


def test_credentials_from_bashrc_last_wins(tmp_path):
    rc = tmp_path / ".bashrc"
    rc.write_text(
        "# jenkins\n"
        "export JENKINS_USER=old\n"
        'export JENKINS_USER="mhamidi"\n'
        "export JENKINS_API_TOKEN='11abc'  # personal token\n"
    )
    assert jc.load_credentials({}, rc) == ("mhamidi", "11abc")


def test_bashrc_fills_only_the_missing_variable(tmp_path):
    rc = tmp_path / ".bashrc"
    rc.write_text("export JENKINS_API_TOKEN=filetok\n")
    assert jc.load_credentials({"JENKINS_USER": "envuser"}, rc) == ("envuser", "filetok")


def test_bashrc_indirection_is_ignored(tmp_path):
    rc = tmp_path / ".bashrc"
    rc.write_text("export JENKINS_USER=u\nexport JENKINS_API_TOKEN=$SOME_OTHER_VAR\n")
    with pytest.raises(jc.MissingCredentials) as e:
        jc.load_credentials({}, rc)
    assert "JENKINS_API_TOKEN" in str(e.value)


def test_missing_credentials_names_both_and_bashrc(tmp_path):
    with pytest.raises(jc.MissingCredentials) as e:
        jc.load_credentials({}, tmp_path / "absent")
    msg = str(e.value)
    assert "JENKINS_USER" in msg and "JENKINS_API_TOKEN" in msg and ".bashrc" in msg


def test_job_path_plain():
    assert jc.job_path("dev") == "/job/dev"


def test_job_path_encodes_slash():
    assert jc.job_path("release/15.0") == "/job/release%2F15.0"


def test_job_path_rejects_empty():
    with pytest.raises(ValueError):
        jc.job_path("")


def test_api_encodes_tree():
    assert jc.api("/job/dev", "lastBuild[number,result]") == \
        "/job/dev/api/json?tree=lastBuild%5Bnumber,result%5D"
    assert jc.api("/job/dev/") == "/job/dev/api/json"


def test_get_json_sends_basic_auth():
    opener = FakeOpener([{"ok": 1}])
    client = jc.JenkinsClient("u", "t", base="https://j.example", opener=opener)
    assert client.get_json("/job/dev/api/json") == {"ok": 1}
    req = opener.requests[0]
    assert req.full_url == "https://j.example/job/dev/api/json"
    assert req.get_header("Authorization") == "Basic " + base64.b64encode(b"u:t").decode()


def test_absolute_urls_are_used_as_is():
    opener = FakeOpener([{}])
    jc.JenkinsClient("u", "t", base="https://j.example", opener=opener).get_json(
        "https://j.example/queue/item/9/api/json")
    assert opener.requests[0].full_url == "https://j.example/queue/item/9/api/json"


def test_401_names_vars_and_hides_token():
    opener = FakeOpener([http_error(401, b"Unauthorized")])
    client = jc.JenkinsClient("u", "s3cret-token", opener=opener)
    with pytest.raises(jc.JenkinsError) as e:
        client.get_json("/job/dev/api/json")
    assert e.value.status == 401
    msg = str(e.value)
    assert "JENKINS_API_TOKEN" in msg and ".bashrc" in msg
    assert "s3cret-token" not in msg


def test_404_keeps_status():
    client = jc.JenkinsClient("u", "t", opener=FakeOpener([http_error(404)]))
    with pytest.raises(jc.JenkinsError) as e:
        client.get_json("/job/nope/api/json")
    assert e.value.status == 404


def test_post_form_returns_lowercased_headers():
    opener = FakeOpener([FakeResponse("", {"Location": "https://j/queue/item/9/"})])
    client = jc.JenkinsClient("u", "t", opener=opener)
    headers = client.post_form("/job/dev/buildWithParameters", [("a", "1"), ("b", "x, y")])
    assert headers["location"] == "https://j/queue/item/9/"
    req = opener.requests[0]
    assert req.get_method() == "POST"
    assert req.data == b"a=1&b=x%2C+y"


def test_post_form_retries_once_with_a_crumb():
    opener = FakeOpener([
        http_error(403, b"No valid crumb was included in the request"),
        {"crumbRequestField": "Jenkins-Crumb", "crumb": "abc"},
        FakeResponse("", {"Location": "https://j/queue/item/9/"}),
    ])
    client = jc.JenkinsClient("u", "t", opener=opener)
    assert client.post_form("/job/dev/buildWithParameters", [])["location"].endswith("/9/")
    assert opener.requests[1].full_url.endswith("/crumbIssuer/api/json")
    assert opener.requests[2].get_header("Jenkins-crumb") == "abc"


def test_post_form_403_without_crumb_is_an_auth_error():
    client = jc.JenkinsClient("u", "t", opener=FakeOpener([http_error(403, b"Forbidden")]))
    with pytest.raises(jc.JenkinsError) as e:
        client.post_form("/job/dev/buildWithParameters", [])
    assert e.value.status == 403


def test_fail_maps_exit_codes(capsys):
    assert jc.fail(jc.MissingCredentials("x")) == jc.EXIT_AUTH
    assert jc.fail(jc.JenkinsError("x", status=403)) == jc.EXIT_AUTH
    assert jc.fail(jc.JenkinsError("x", status=404)) == jc.EXIT_NOT_FOUND
    assert jc.fail(jc.JenkinsError("x", status=500)) == jc.EXIT_ERROR
    assert "ERROR:" in capsys.readouterr().err
