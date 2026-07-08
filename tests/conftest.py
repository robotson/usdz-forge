"""Shared fixtures: fetch-and-cache Khronos sample assets, run the engine."""
import os
import subprocess
import urllib.request

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_DIR)
FIXTURES_DIR = os.path.join(TESTS_DIR, "fixtures")
OUTPUT_DIR = os.path.join(TESTS_DIR, "output")

ENGINE_PYTHON = os.path.join(REPO_ROOT, "engine", "python", "bin", "python3.14")
USDZCONVERT = os.path.join(REPO_ROOT, "engine", "native", "usdzconvert")

KHRONOS_BASE = ("https://raw.githubusercontent.com/KhronosGroup/"
                "glTF-Sample-Assets/main/Models/{name}/glTF-Binary/{name}.glb")


@pytest.fixture(scope="session", autouse=True)
def clean_output_dir():
    """Wipe tests/output at session START (not end): every run gets a clean
    slate — no orphans from renamed tests — while the latest run's artifacts
    stay on disk for post-mortem inspection. (Fixtures cache is kept: those
    are downloads, not products.)"""
    import shutil
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    yield


def fetch_fixture(name):
    """Download a Khronos sample GLB once; cache under tests/fixtures/."""
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    dest = os.path.join(FIXTURES_DIR, name + ".glb")
    if not os.path.exists(dest):
        url = KHRONOS_BASE.format(name=name)
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as exc:  # offline / upstream moved
            pytest.skip("could not fetch fixture %s: %s" % (name, exc))
    return dest


def convert(glb_path, out_name):
    """Run the engine; return (usdz_path, exit_code, combined_output)."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, out_name + ".usdz")
    if os.path.exists(out_path):
        os.remove(out_path)
    proc = subprocess.run(
        [ENGINE_PYTHON, USDZCONVERT, glb_path, out_path],
        capture_output=True, text=True, timeout=300,
    )
    return out_path, proc.returncode, proc.stdout + proc.stderr
