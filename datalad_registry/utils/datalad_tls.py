from dataclasses import dataclass
import re
from typing import Optional
from uuid import UUID

from datalad import api as dl
from datalad.api import Dataset


@dataclass
class WtAnnexedFileInfo:
    """
    Represent information about annexed files in the working tree of a datalad dataset
    that is a git-annex repo
    """

    count: int
    size: int


def clone(*args, **kwargs) -> dl.Dataset:
    """
    Clone (copy) a dataset from a given URL or local directory

    All parameters of this function are the same as `datalad.api.clone` with the
    exception that the keyword parameter `return_type` is not supported.

    :raises TypeError: Calling this function with the keyword argument of `return_type`
    :raises RuntimeError: If the cloning process fails to produce
                          a `datalad.api.Dataset` object even after successfully
                          copying the dataset from the given URL or local directory
    :return: A `datalad.api.Dataset` object representing the clone/copy of the dataset
    """
    if "return_type" in kwargs:
        raise TypeError("'return_type' is not a supported keyword argument")

    ds = dl.clone(*args, return_type="item-or-list", **kwargs)

    # Ensure that a Dataset object is produced upon a successful cloning
    if not isinstance(ds, dl.Dataset):
        raise RuntimeError("Cloning of a dataset failed to produce a Dataset object")

    return ds


def get_origin_annex_uuid(ds: Dataset) -> Optional[UUID]:
    """
    Get the annex UUID of the origin remote of a given dataset

    :param ds: The dataset
    :return: The annex UUID of the origin remote of the given dataset if it exists;
             None otherwise.
    """

    return (
        UUID(uuid_str)
        if (uuid_str := ds.config.get("remote.origin.annex-uuid")) is not None
        else None
    )


def get_origin_annex_key_count(ds: Dataset) -> Optional[int]:
    """
    Get "remote annex keys" of the origin remote of a given dataset

    :param ds: The given dataset
    :return: In the case that the dataset is a git-annex repo, the "remote annex keys"
             of the origin remote of the given dataset is returned.
             In the case that the dataset is not a git-annex repo, return None.
    """
    if ds.repo.is_with_annex():
        return ds.repo.call_annex_records(["info"], "origin")[0]["remote annex keys"]
    else:
        return None


def get_wt_annexed_file_info(ds: Dataset) -> Optional[WtAnnexedFileInfo]:
    """
    Get information about annexed files in the working tree of a given datalad dataset

    :param ds: The given dataset
    :return: In the case that the dataset is a git-annex repo, information about
             annexed files in the working tree of the dataset is returned.
             In the case that the dataset is not a git-annex repo, return None.
    """
    if ds.repo.is_with_annex():
        annex_record = ds.repo.call_annex_records(["info", "--bytes"], ".")[0]

        return WtAnnexedFileInfo(
            count=annex_record["annexed files in working tree"],
            size=int(annex_record["size of annexed files in working tree"]),
        )
    else:
        return None


def get_head_describe(ds: Dataset) -> str:
    """
    Get the output of `git describe --tags --always` of a given dataset

    :param ds: The given dataset
    :return: The output of `git describe --tags --always` of the given dataset
    """
    return ds.repo.describe(tags=True, always=True)


def get_origin_branches(ds: Dataset) -> dict[str, dict[str, str]]:
    """
    Get the branches of the origin remote of a given dataset

    :param ds: The given dataset
    :return: A dictionary representing the branches of the origin remote
             of the given dataset. Each branch is represented by a key-value pair in
             which the key is the branch name and the value is a dictionary with keys,
             "hexsha" and "last_commit_dt".
             The value of "hexsha" is the hash of the last commit in the branch,
             and the value of "last_commit_dt" is the datetime of the last commit
             in the branch.
    """
    return {
        branch_name: {
            "hexsha": branch_info["objectname"],
            "last_commit_dt": branch_info["authordate:iso8601-strict"],
        }
        for branch_info in ds.repo.for_each_ref_(
            pattern="refs/remotes/origin/",
            fields=["objectname", "refname:strip=3", "authordate:iso8601-strict"],
        )
        if (branch_name := branch_info["refname:strip=3"]) != "HEAD"
    }


def get_origin_default_branch(ds: Dataset) -> str:
    """
    Get the name of the default branch of the origin remote of a given dataset

    :param ds: The given dataset
    :return: The name of the default branch of the origin remote of the given dataset

    Note: The given dataset must be a git repo with a remote named "origin"
    """
    ls_remote_output = ds.repo.call_git(["ls-remote", "--symref", "origin", "HEAD"])

    match = re.search(r"ref: refs/heads/(\S+)\s+HEAD", ls_remote_output)

    if match is None:
        raise RuntimeError(
            "Failed to extract the name of the default branch of the original remote "
            "from the output of `git ls-remote --symref origin HEAD`"
        )

    return match.group(1)


def get_origin_upstream_branch(ds: Dataset) -> str:
    """
    Get the name of the upstream branch at the origin remote of the current local branch
    of a given dataset

    :param ds: The given dataset
    :return: The name of the upstream branch at the origin remote of the current local
             branch of the given dataset

    Note: The given dataset must be a git repo with a remote named "origin"
    """
    rev_parse_output = ds.repo.call_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
    )

    match = re.search(r"origin/(\S+)", rev_parse_output)

    if match is None:
        raise RuntimeError(
            "Failed to extract the name of the upstream branch at the origin remote "
            "of the current local branch from the output of "
            "`git rev-parse --abbrev-ref --symbolic-full-name @{u}`"
        )

    return match.group(1)
