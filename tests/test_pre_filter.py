"""Tests for PreFilter (TC-002)."""

from dep_agent.filtering.pre_filter import PreFilter


def test_prefilter_init() -> None:
    """PreFilter should initialize with config."""
    pf = PreFilter()
    assert pf._compiled_noise is not None
    assert pf._compiled_contract is not None


def test_filter_merge_commit() -> None:
    """Merge commits should be dropped."""
    pf = PreFilter()
    result = pf.evaluate([{"sha": "abc123", "author": "user", "message": "Merge pull request #123", "changed_files": ["file.py"]}])
    assert result.total == 1
    assert result.dropped == 1
    assert result.kept == 0
    assert result.results[0].reason == "noise:merge"


def test_filter_chore_commit() -> None:
    """Chore commits should be dropped."""
    pf = PreFilter()
    result = pf.evaluate([{"sha": "abc123", "author": "user", "message": "chore: update dependencies", "changed_files": ["requirements.txt"]}])
    assert result.dropped == 1
    assert result.results[0].reason == "noise:chore"


def test_filter_docs_commit() -> None:
    """Docs commits should be dropped."""
    pf = PreFilter()
    result = pf.evaluate([{"sha": "abc123", "author": "user", "message": "docs: update README", "changed_files": ["README.md"]}])
    assert result.dropped == 1


def test_filter_lint_commit() -> None:
    """Lint commits should be dropped."""
    pf = PreFilter()
    result = pf.evaluate([{"sha": "abc123", "author": "user", "message": "lint: fix formatting", "changed_files": ["file.py"]}])
    assert result.dropped == 1


def test_filter_typo_commit() -> None:
    """Typo commits should be dropped."""
    pf = PreFilter()
    result = pf.evaluate([{"sha": "abc123", "author": "user", "message": "typo: fix grammar", "changed_files": ["docs.md"]}])
    assert result.dropped == 1


def test_filter_openapi_commit() -> None:
    """OpenAPI contract changes should be kept."""
    pf = PreFilter()
    result = pf.evaluate([{"sha": "abc123", "author": "user", "message": "feat: update billing API schema", "changed_files": ["openapi/billing.yaml"]}])
    assert result.kept == 1
    assert result.dropped == 0
    assert result.results[0].artifact_type == "openapi_contract"


def test_filter_protobuf_commit() -> None:
    """Protobuf changes should be kept."""
    pf = PreFilter()
    result = pf.evaluate([{"sha": "abc123", "author": "user", "message": "feat: add new message type", "changed_files": ["proto/user/v1/user.proto"]}])
    assert result.kept == 1
    assert result.results[0].artifact_type == "protobuf"


def test_filter_package_manifest_commit() -> None:
    """Package manifest changes should be kept."""
    pf = PreFilter()
    result = pf.evaluate([{"sha": "abc123", "author": "user", "message": "feat: add new dependency", "changed_files": ["package.json"]}])
    assert result.kept == 1
    assert result.results[0].artifact_type == "package_manifest"


def test_filter_non_contract_commit() -> None:
    """Non-contract file changes should be dropped."""
    pf = PreFilter()
    result = pf.evaluate([{"sha": "abc123", "author": "user", "message": "feat: add new feature", "changed_files": ["src/app.py"]}])
    assert result.dropped == 1
    assert result.results[0].reason == "no_contract_match"


def test_filter_batch_mixed() -> None:
    """Batch with mixed commits should filter correctly."""
    pf = PreFilter()
    commits = [
        {"sha": "1", "author": "a", "message": "Merge pull request", "changed_files": ["file.py"]},
        {"sha": "2", "author": "b", "message": "feat: update API schema", "changed_files": ["openapi/api.yaml"]},
        {"sha": "3", "author": "c", "message": "chore: cleanup", "changed_files": ["README.md"]},
        {"sha": "4", "author": "d", "message": "feat: add proto", "changed_files": ["proto/test.proto"]},
    ]
    result = pf.evaluate(commits)
    assert result.total == 4
    assert result.kept == 2
    assert result.dropped == 2


def test_is_contract_path() -> None:
    """is_contract_path should return True for contract paths."""
    pf = PreFilter()
    assert pf.is_contract_path("openapi/api.yaml") is True
    assert pf.is_contract_path("proto/test.proto") is True
    assert pf.is_contract_path("package.json") is True
    assert pf.is_contract_path("src/app.py") is False


def test_get_artifact_type() -> None:
    """get_artifact_type should return correct type."""
    pf = PreFilter()
    assert pf.get_artifact_type("openapi/billing.yaml") == "openapi_contract"
    assert pf.get_artifact_type("proto/user.proto") == "protobuf"
    assert pf.get_artifact_type("go.mod") == "package_manifest"
    assert pf.get_artifact_type("src/app.py") is None
