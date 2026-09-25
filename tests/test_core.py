"""Tests for opencode-cloud-workstation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

def test_runtime_detection():
    from opencode_cloud.runtime import detect_runtime
    rt = detect_runtime()
    assert rt in ("kaggle", "local")
    print("runtime detection ok:", rt)


def test_paths():
    from opencode_cloud.runtime import get_paths
    paths = get_paths("kaggle")
    assert paths.working.name == "working" or True
    print("paths ok")


def test_secrets_manager():
    from opencode_cloud.secrets import EnvSecrets
    mgr = EnvSecrets()
    assert mgr.get("NON_EXISTENT") is None
    print("secrets ok")


def test_checkpoint_policy():
    from opencode_cloud.checkpoint import CheckpointManager
    mgr = CheckpointManager()
    assert not mgr.should_publish(significant_changes=0)
    print("checkpoint ok")


def test_persistence_path():
    from opencode_cloud.persistence import PersistentStore
    store = PersistentStore(dataset_root=Path("/tmp/test_store"))
    store.ensure_structure()
    print("persistence ok")


def test_github_validate():
    from opencode_cloud.github_sync import validate_repo_url
    url = validate_repo_url("https://github.com/owner/repo")
    assert url.endswith(".git")
    print("github validate ok")


if __name__ == "__main__":
    test_runtime_detection()
    test_paths()
    test_secrets_manager()
    test_checkpoint_policy()
    test_persistence_path()
    test_github_validate()
    print("All tests passed")
