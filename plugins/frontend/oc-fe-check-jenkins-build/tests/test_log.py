import json

import jenkins_log as lg
from conftest import FakeClient

CONSOLE = """[Pipeline] { (Build Meveo)
[INFO] BUILD SUCCESS
[Pipeline] }
[Pipeline] { (Checkout Front)
Cloning git@bitbucket.org:opencellsoft/opencell-portal.git
[Pipeline] }
[Pipeline] { (Build Front)
$ yarn build
src/pages/Invoice.tsx(12,7): error TS2339: Property 'total' does not exist on type 'Invoice'.
error Command failed with exit code 2.
[Pipeline] }
[Pipeline] { (kc config)
Stage "kc config" skipped due to earlier failure(s)
"""


def test_slice_console_returns_only_the_stage():
    part = lg.slice_console(CONSOLE, "Build Front")
    assert part.startswith("[Pipeline] { (Build Front)")
    assert "error TS2339" in part
    assert "kc config" not in part and "Cloning" not in part


def test_slice_console_last_stage_runs_to_end():
    assert lg.slice_console(CONSOLE, "kc config").endswith("earlier failure(s)\n")


def test_slice_console_missing_stage():
    assert lg.slice_console(CONSOLE, "Nope") == ""


def test_error_lines_dedup_and_cap():
    text = "\n".join(["error TS1005: ';' expected."] * 3 + [f"npm ERR! {i}" for i in range(100)])
    lines = lg.error_lines(text, limit=5)
    assert lines[0] == "error TS1005: ';' expected."
    assert len(lines) == 5 and len(set(lines)) == 5


def test_error_lines_ignore_noise():
    assert lg.error_lines("adding: storybook/assets/x.js (deflated 42%)\n[INFO] BUILD SUCCESS") == []


def test_classify():
    assert lg.classify("src/a.ts(1,1): error TS2304: Cannot find name 'x'.") == "code"
    assert lg.classify('[vite]: Rollup failed to resolve import "foo"') == "code"
    assert lg.classify("  12:5  error  'x' is defined but never used  no-unused-vars") == "code"
    assert lg.classify("npm ERR! network request failed, reason: connect ETIMEDOUT") == "infra"
    assert lg.classify("scp: Permission denied (publickey).") == "infra"
    assert lg.classify("No space left on device") == "infra"
    assert lg.classify("ETIMEDOUT\nerror TS2304: Cannot find name 'x'.") == "code"
    assert lg.classify("script returned exit code 1") == "unknown"


def test_clean_unescapes_html():
    assert lg.clean('<span class="x">Type &lt;string&gt; &amp; more</span>') == "Type <string> & more"


def test_console_text_is_never_cleaned():
    console = ("[Pipeline] { (Build Front)\n"
               "error TS2322: Type 'Array<string>' is not assignable.\n"
               "  3 | <span className=\"x\">{a}</span>\n"
               "x => y && a < b\nmore text > here\n")
    text, source = lg.stage_log(FakeClient({"/job/dev/4970/consoleText": console}),
                                "dev", 4970, None, "Build Front")
    assert source == "console" and text == console


def test_step_log_text_is_always_unescaped():
    client = FakeClient({
        "/job/dev/4970/execution/node/132/wfapi/describe": describe_node(("140", "FAILED")),
        "/job/dev/4970/execution/node/140/wfapi/log": {"text": "Type &#39;Array&lt;string&gt;&#39;\n"},
    })
    text, _ = lg.stage_log(client, "dev", 4970, "132", "Build Front")
    assert text.strip() == "Type 'Array<string>'"


def test_checkout_front_is_never_code():
    assert lg.classify("error TS2304: x", stage="Checkout Front") == "infra"


def test_ssh_resolve_hostname_is_infra():
    assert lg.classify("ssh: Could not resolve hostname bitbucket.org\n"
                       "fatal: Could not read from remote repository.") == "infra"


def test_bundler_could_not_resolve_is_code():
    assert lg.classify('✘ [ERROR] Could not resolve "lodash-es"') == "code"


def test_gateway_error_beats_syntax_error():
    assert lg.classify("npm ERR! SyntaxError: Unexpected token < in JSON (502 Bad Gateway)") == "infra"


def test_tail():
    assert lg.tail("a\nb\nc\nd", 2) == "c\nd"


def describe_node(*nodes):
    return {"stageFlowNodes": [{"id": i, "status": s} for i, s in nodes]}


def test_stage_log_prefers_failed_step_nodes():
    client = FakeClient({
        "/job/dev/4970/execution/node/132/wfapi/describe": describe_node(("135", "SUCCESS"), ("140", "FAILED")),
        "/job/dev/4970/execution/node/140/wfapi/log": {"text": "error TS2304: x\n", "hasMore": False},
    })
    text, source = lg.stage_log(client, "dev", 4970, "132", "Build Front")
    assert source == "step-log" and "TS2304" in text
    assert not any("/node/135/" in c for c in client.calls)


def test_stage_log_falls_back_to_console():
    client = FakeClient({
        "/job/dev/4970/execution/node/132/wfapi/describe": describe_node(("140", "FAILED")),
        "/job/dev/4970/execution/node/140/wfapi/log": {"text": "", "hasMore": False},
        "/job/dev/4970/consoleText": CONSOLE,
    })
    text, source = lg.stage_log(client, "dev", 4970, "132", "Build Front")
    assert source == "console" and "TS2339" in text and "Cloning" not in text


def test_stage_log_without_stage_id_uses_console():
    client = FakeClient({"/job/dev/4970/consoleText": CONSOLE})
    text, source = lg.stage_log(client, "dev", 4970, None, "Build Front")
    assert source == "console" and "TS2339" in text


def test_main_prints_classification(capsys):
    client = FakeClient({"/job/dev/4970/consoleText": CONSOLE})
    assert lg.main(["--branch", "dev", "--build", "4970", "--stage", "Build Front"], client=client) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["classification"] == "code" and out["source"] == "console"
    assert any("TS2339" in line for line in out["error_lines"])
    assert "TS2339" in out["excerpt"]
