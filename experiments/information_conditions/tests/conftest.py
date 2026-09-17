import sys
from pathlib import Path

import pytest

EXP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP_DIR))

from infocond.common import load_config  # noqa: E402
from infocond import conditions, data  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture(scope="session")
def datasets_ready(cfg):
    data.ensure_full_datasets(cfg)
    return data.verify_datasets(cfg)


@pytest.fixture(scope="session")
def bundles(cfg, datasets_ready):
    return conditions.build_all_bundles(cfg)


@pytest.fixture(scope="session")
def by_key(bundles):
    return {(b["dataset"], b["condition"]): b for b in bundles}
