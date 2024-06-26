from pathlib import Path
from uuid import UUID

from datalad.api import Dataset
import pytest

from datalad_registry.utils.datalad_tls import (
    WtAnnexedFileInfo,
    clone,
    get_origin_annex_key_count,
    get_origin_annex_uuid,
    get_origin_branches,
    get_origin_default_branch,
    get_origin_upstream_branch,
    get_wt_annexed_file_info,
)

_TEST_MIN_DATASET_URL = "https://github.com/datalad/testrepo--minimalds.git"
_TEST_MIN_DATASET_ID = "e7f3d914-e971-11e8-a371-f0d5bf7b5561"


class TestClone:
    @pytest.mark.parametrize(
        "return_type",
        ["generator", "list", "item-or-list"],
    )
    def test_unsupported_kwarg(self, tmp_path, return_type):
        """
        Test the case that the unsupported keyword argument of `return_type`
        is provided
        """
        with pytest.raises(TypeError):
            clone(source=_TEST_MIN_DATASET_URL, path=tmp_path, return_type=return_type)

    @pytest.mark.parametrize(
        "clone_return",
        [None, list(), ["a", "b", "c"]],
    )
    def test_no_dataset_object_produced(self, monkeypatch, tmp_path, clone_return):
        """
        Test the case that no `datalad.api.Dataset` object is produced after
        a successful run of the underlying `datalad.api.clone` function
        """
        from datalad import api as dl

        # noinspection PyUnusedLocal
        def mock_clone(*args, **kwargs):  # noqa: U100 (unused argument)
            return clone_return

        monkeypatch.setattr(dl, "clone", mock_clone)

        with pytest.raises(RuntimeError):
            clone(source=_TEST_MIN_DATASET_URL, path=tmp_path)

    def test_clone_minimal_dataset(self, tmp_path):
        """
        Test cloning a minimal dataset used for testing
        """
        ds = clone(source=_TEST_MIN_DATASET_URL, path=tmp_path)
        assert ds.id == _TEST_MIN_DATASET_ID


class TestGetOriginAnnexUuid:
    @pytest.mark.parametrize("ds_name", ["empty_ds_annex", "two_files_ds_annex"])
    def test_annex_repo(self, ds_name, request, tmp_path):
        """
        Test the case that the origin remote is a git-annex repo
        """
        ds = request.getfixturevalue(ds_name)
        ds_clone = clone(source=ds.path, path=tmp_path)
        assert get_origin_annex_uuid(ds_clone) == UUID(ds.config.get("annex.uuid"))

    @pytest.mark.parametrize(
        "ds_name", ["empty_ds_non_annex", "two_files_ds_non_annex"]
    )
    def test_non_annex_repo(self, ds_name, request, tmp_path):
        """
        Test the case that the origin remote is not a git-annex repo
        """
        ds = request.getfixturevalue(ds_name)
        ds_clone = clone(source=ds.path, path=tmp_path)
        assert get_origin_annex_uuid(ds_clone) is None

    def test_origin_annex_uuid_not_exist(self, tmp_path):
        """
        Test the case that the origin remote has no annex UUID even though it is an
        annex repo
        """
        ds = clone(source=_TEST_MIN_DATASET_URL, path=tmp_path)
        assert get_origin_annex_uuid(ds) is None


class TestGetOriginAnnexKeyCount:
    @pytest.mark.parametrize(
        "ds_name, expected_annex_key_count",
        [("empty_ds_annex", 0), ("two_files_ds_annex", 2)],
    )
    def test_annex_repo(self, ds_name, expected_annex_key_count, request, tmp_path):
        """
        Test the case that the origin remote is a git-annex repo
        """
        ds = request.getfixturevalue(ds_name)
        ds_clone = clone(source=ds.path, path=tmp_path)
        annex_key_count = get_origin_annex_key_count(ds_clone)
        assert type(annex_key_count) is int
        assert annex_key_count == expected_annex_key_count

    @pytest.mark.parametrize(
        "ds_name", ["empty_ds_non_annex", "two_files_ds_non_annex"]
    )
    def test_non_annex_repo(self, ds_name, request, tmp_path):
        """
        Test the case that the origin remote is not a git-annex repo
        """
        ds = request.getfixturevalue(ds_name)
        ds_clone = clone(source=ds.path, path=tmp_path)
        assert get_origin_annex_key_count(ds_clone) is None


class TestGetWtAnnexedFileInfo:
    @pytest.mark.parametrize(
        "ds_name, expected_info",
        [
            ("empty_ds_annex", WtAnnexedFileInfo(0, 0)),
            ("two_files_ds_annex", WtAnnexedFileInfo(2, 38)),
        ],
    )
    def test_annex_repo(self, ds_name, expected_info, request):
        """
        Test the case that the given dataset is a git-annex repo
        """
        ds = request.getfixturevalue(ds_name)
        wt_annexed_file_info = get_wt_annexed_file_info(ds)
        assert wt_annexed_file_info == expected_info

    @pytest.mark.parametrize(
        "ds_name", ["empty_ds_non_annex", "two_files_ds_non_annex"]
    )
    def test_non_annex_repo(self, ds_name, request):
        """
        Test the case that the given dataset is not a git-annex repo
        """
        ds = request.getfixturevalue(ds_name)
        assert get_wt_annexed_file_info(ds) is None


@pytest.mark.parametrize(
    "ds_name",
    [
        "empty_ds_annex",
        "two_files_ds_annex",
        "empty_ds_non_annex",
        "two_files_ds_non_annex",
    ],
)
def test_get_origin_branches(ds_name, request, tmp_path):
    ds: Dataset = request.getfixturevalue(ds_name)
    ds_clone = clone(source=ds.path, path=tmp_path)

    origin_branches = get_origin_branches(ds_clone)

    branch_names = set(ds.repo.get_branches())

    assert set(origin_branches) == branch_names

    for o_b_name, o_b_data in origin_branches.items():
        assert o_b_data == {
            "hexsha": ds.repo.get_hexsha(o_b_name),
            "last_commit_dt": ds.repo.call_git(
                ["log", "-1", "--format=%aI", o_b_name]
            ).strip(),
        }


def _mock_no_match_re_search(*_args, **_kwargs):
    return None


def _two_level_clone(ds: Dataset, dir_path: Path) -> tuple[Dataset, Dataset]:
    """
    Do a two-level clone of a given dataset within a given directory

    :param ds: The given directory
    :param dir_path: The given directory, which must be empty
    :return: A tuple consisting of the first and second level clones
             of the given dataset each residing in a subdirectory of the given directory
    """
    l1_clone_path = dir_path / "l1_clone"
    l2_clone_path = dir_path / "l2_clone"

    l1_clone = clone(source=ds.path, path=l1_clone_path)
    l2_clone = clone(source=l1_clone.path, path=l2_clone_path)

    return l1_clone, l2_clone


class TestGetOriginDefaultBranch:
    def test_no_match(self, two_files_ds_non_annex, tmp_path, monkeypatch):
        """
        Test the case that the default branch name of the origin remote of the given
        dataset can't be extracted from the output of `git ls-remote`
        """

        ds_clone = clone(source=two_files_ds_non_annex.path, path=tmp_path)

        with pytest.raises(RuntimeError, match="Failed to extract the name"):
            with monkeypatch.context() as m:
                import re

                m.setattr(re, "search", _mock_no_match_re_search)
                get_origin_default_branch(ds_clone)

    @pytest.mark.parametrize(
        "ds_name",
        [
            "empty_ds_annex",
            "two_files_ds_annex",
            "empty_ds_non_annex",
            "two_files_ds_non_annex",
        ],
    )
    @pytest.mark.parametrize("branch_name", ["foo", "bar"])
    def test_normal_operation(self, ds_name, branch_name, request, tmp_path):
        """
        Test the normal operation of `get_origin_default_branch`
        """
        ds: Dataset = request.getfixturevalue(ds_name)

        l1_clone, l2_clone = _two_level_clone(ds, tmp_path)

        l1_clone.repo.call_git(["checkout", "-b", branch_name])

        assert get_origin_default_branch(l2_clone) == branch_name


class TestGetOriginUpstreamBranch:
    def test_no_match(self, two_files_ds_non_annex, tmp_path, monkeypatch):
        """
        Test the case that the name of the upstream branch at the origin remote of
        the current local branch of a given dataset can't be extracted from the output
        of `git rev-parse`
        """

        ds_clone = clone(source=two_files_ds_non_annex.path, path=tmp_path)

        with pytest.raises(RuntimeError, match="Failed to extract the name"):
            with monkeypatch.context() as m:
                import re

                m.setattr(re, "search", _mock_no_match_re_search)
                get_origin_upstream_branch(ds_clone)

    @pytest.mark.parametrize(
        "ds_name",
        [
            "empty_ds_annex",
            "two_files_ds_annex",
            "empty_ds_non_annex",
            "two_files_ds_non_annex",
        ],
    )
    @pytest.mark.parametrize("branch_name", ["foo", "bar"])
    def test_normal_operation(self, ds_name, branch_name, request, tmp_path):
        """
        Test the normal operation of `get_origin_upstream_branch`
        """
        ds: Dataset = request.getfixturevalue(ds_name)

        _, l2_clone = _two_level_clone(ds, tmp_path)

        l2_clone.repo.call_git(["checkout", "-b", branch_name])
        l2_clone.repo.call_git(["push", "-u", "origin", branch_name])

        assert get_origin_upstream_branch(l2_clone) == branch_name
