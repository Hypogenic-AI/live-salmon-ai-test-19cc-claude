"""
Run model-written Python on the explorer's own data, in a locked-down Docker container.

Every block runs in a fresh container built from sandbox/Dockerfile, with no network, a
read-only file system (apart from a small /tmp), an unprivileged user, no Linux
capabilities, and limits on memory, CPU, processes and time. The only host file it can
see is a CSV of the runs collected so far, mounted read-only at /data/runs.csv and
loaded as the pandas DataFrame `df`.

    docker build -t salmon-lab-sandbox:1 experiments/salmon_lab/sandbox
"""

import csv
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

IMAGE = "salmon-lab-sandbox:1"
TIMEOUT = 60  # seconds per block
MAX_OUTPUT = 8000  # characters of printed output returned per block


def write_table(columns, rows, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        w.writerows(rows)


def docker_command(name, data_dir, timeout):
    return [
        "docker", "run", "--rm", "-i", "--name", name,
        "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,size=64m",
        "--memory", "1g", "--memory-swap", "1g", "--cpus", "1", "--pids-limit", "64",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "65534:65534",
        "-e", "HOME=/tmp", "-e", "MPLCONFIGDIR=/tmp",
        "-v", f"{data_dir}:/data:ro",
        IMAGE, "timeout", "-s", "KILL", str(timeout), "python", "/opt/runner.py",
    ]


def run_code(code, columns, rows, timeout=TIMEOUT):
    """Run one block. Returns exit code, printed output (cut to MAX_OUTPUT), time taken."""
    name = f"salmon-lab-{uuid.uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory() as data_dir:
        write_table(columns, rows, Path(data_dir) / "runs.csv")
        start = time.monotonic()
        try:
            proc = subprocess.run(docker_command(name, data_dir, timeout), input=code,
                                  capture_output=True, text=True, timeout=timeout + 30)
            exit_code, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            subprocess.run(["docker", "kill", name], capture_output=True)
            exit_code, out, err = 137, e.stdout or "", e.stderr or ""
            out, err = (out.decode() if isinstance(out, bytes) else out), (err.decode() if isinstance(err, bytes) else err)
        seconds = round(time.monotonic() - start, 1)
    timed_out = exit_code == 137
    output = out + (("\n" if out and not out.endswith("\n") else "") + err if err else "")
    truncated = len(output) > MAX_OUTPUT
    return {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "output": output[:MAX_OUTPUT],
        "truncated": truncated,
        "seconds": seconds,
    }


def available():
    """True when the Docker daemon is running and the sandbox image exists."""
    try:
        return subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
