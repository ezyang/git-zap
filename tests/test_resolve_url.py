import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
from git_zap.cli import _resolve_url


def test_absolute_https_url_unchanged():
    base = "git@github.com:pytorch/pytorch.git"
    url = "https://github.com/nlohmann/json.git"
    assert _resolve_url(base, url) == url


def test_absolute_ssh_url_unchanged():
    base = "git@github.com:pytorch/pytorch.git"
    url = "git@github.com:nlohmann/json.git"
    assert _resolve_url(base, url) == url


def test_relative_url_single_parent_ssh():
    # ../dynolog.git from pytorch/kineto.git goes up to root, giving dynolog.git
    base = "git@github.com:pytorch/kineto.git"
    url = "../dynolog.git"
    assert _resolve_url(base, url) == "git@github.com:dynolog.git"


def test_relative_url_sibling_ssh():
    # For sibling repos in same org, use ./sibling.git not ../sibling.git
    base = "git@github.com:owner/repo.git"
    url = "./sibling.git"
    assert _resolve_url(base, url) == "git@github.com:owner/sibling.git"


def test_relative_url_https():
    # Same semantics as SSH: ../kineto.git goes up from pytorch/ to root
    base = "https://github.com/pytorch/pytorch.git"
    url = "../kineto.git"
    assert _resolve_url(base, url) == "https://github.com/kineto.git"


def test_relative_url_current_dir():
    base = "git@github.com:owner/repo.git"
    url = "./other.git"
    assert _resolve_url(base, url) == "git@github.com:owner/other.git"


def test_relative_url_nested_path():
    # For a repo with nested path, ../ goes up one level
    base = "git@github.com:org/project/subrepo.git"
    url = "../sibling.git"
    assert _resolve_url(base, url) == "git@github.com:org/sibling.git"
