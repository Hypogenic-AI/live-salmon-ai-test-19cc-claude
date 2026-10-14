"""
Checks on the code sandbox: the model's code sees its data and nothing else, cannot reach
the network or change files, and is stopped when it runs too long. Needs Docker and the
sandbox image; skipped otherwise.
"""

import pytest

import sandbox
from world import LabWorld

pytestmark = pytest.mark.skipif(not sandbox.available(), reason="Docker or the sandbox image is not available")


@pytest.fixture(scope="module")
def world():
    w = LabWorld(0)
    w.run_experiments([{"n": 30}, {"set": {"X4": 2, "X5": -1.5}, "n": 5}])
    return w


def run(code, world, **kw):
    return sandbox.run_code(code, *world.code_table(), **kw)


def test_code_sees_its_runs_as_df(world):
    r = run("print(df.shape); print(list(df.columns)[:3], list(df.columns)[-2:]); print(df['set'].iloc[-1])", world)
    assert r["exit_code"] == 0
    assert "(35, 23)" in r["output"] and "['run', 'X1', 'X2'] ['Y', 'set']" in r["output"]
    assert "X4=2; X5=-1.5" in r["output"]


def test_analysis_libraries_work(world):
    code = "import statsmodels.formula.api as smf\nprint(round(smf.ols('Y ~ X1 + X4:X5', data=df).fit().params['X1'], 1))"
    assert run(code, world)["exit_code"] == 0


def test_no_network(world):
    code = ("import socket\ns = socket.socket()\ns.settimeout(3)\n"
            "try:\n    s.connect(('1.1.1.1', 53)); print('CONNECTED')\nexcept OSError as e:\n    print('blocked')")
    assert run(code, world)["output"].strip() == "blocked"


def test_files_are_read_only_except_tmp(world):
    code = ("import os\n"
            "for p in ['/opt/x', '/data/x', '/home/x', '/tmp/x']:\n"
            "    try:\n        open(p, 'w').write('x'); print(p, 'writable')\n"
            "    except OSError:\n        print(p, 'blocked')\n"
            "print('host home visible:', os.path.exists('/Users'))\nprint('uid', os.getuid())")
    out = run(code, world)["output"]
    for p in ["/opt/x", "/data/x", "/home/x"]:
        assert f"{p} blocked" in out
    assert "/tmp/x writable" in out and "host home visible: False" in out and "uid 65534" in out


def test_long_runs_are_stopped(world):
    r = run("while True:\n    pass", world, timeout=3)
    assert r["timed_out"] and r["seconds"] < 30


def test_long_output_is_cut(world):
    r = run("print('a' * 20000)", world)
    assert r["truncated"] and len(r["output"]) == sandbox.MAX_OUTPUT


def test_errors_come_back_as_tracebacks(world):
    r = run("x = 1\ny = x / 0", world)
    assert r["exit_code"] != 0 and "ZeroDivisionError" in r["output"] and "<your code>" in r["output"]
