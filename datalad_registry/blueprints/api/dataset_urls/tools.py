from sqlalchemy import (
    CTE,
    ScalarSelect,
    Select,
    Subquery,
    and_,
    func,
    not_,
    or_,
    select,
)

from datalad_registry.models import RepoUrl, db

from .models import CollectionStats


def _get_annex_ds_collection_stats(q: Subquery) -> ScalarSelect:
    """
    Get the stats of a collection of datasets that contains only of annex datasets

    :param q: The query that specifies the collection of datasets under consideration
    :return: The scalar selectable for obtaining the stats

    Note: The execution of this function requires the Flask app's context
    """

    return (
        select(
            func.jsonb_build_object(
                "ds_count",
                func.count(),
                "annexed_files_size",
                func.sum(q.c.annexed_files_in_wt_size),
                "annexed_file_count",
                func.sum(q.c.annexed_files_in_wt_count),
            ).label("annex_ds_collection_stats")
        )
        .select_from(q)
        .scalar_subquery()
    )


def get_unique_dl_ds_collection_stats(base_cte: CTE) -> ScalarSelect:
    """
    Get the stats of the subset of the collection of datasets that contains only
    of Datalad datasets, considering datasets with the same `ds_id` as the same
    dataset

    :param base_cte: The base CTE that specified the collection of datasets
        under consideration
    :return: The scalar selectable for obtaining the stats

    Note: The execution of this function requires the Flask app's context
    """

    grp_by_id_q = (
        select(
            base_cte.c.ds_id,
            func.max(base_cte.c.annexed_files_in_wt_size).label(
                "max_annexed_files_in_wt_size"
            ),
        )
        .group_by(base_cte.c.ds_id)
        .subquery("grp_by_id_q")
    )

    grp_by_id_and_a_f_size_q = (
        select(
            RepoUrl.ds_id,
            RepoUrl.annexed_files_in_wt_size,
            func.max(RepoUrl.annexed_files_in_wt_count).label(
                "annexed_files_in_wt_count"
            ),
        )
        .join(
            grp_by_id_q,
            and_(
                RepoUrl.ds_id == grp_by_id_q.c.ds_id,
                or_(
                    grp_by_id_q.c.max_annexed_files_in_wt_size.is_(None),
                    RepoUrl.annexed_files_in_wt_size
                    == grp_by_id_q.c.max_annexed_files_in_wt_size,
                ),
            ),
        )
        .group_by(RepoUrl.ds_id, RepoUrl.annexed_files_in_wt_size)
        .subquery("grp_by_id_and_a_f_size_q")
    )

    return _get_annex_ds_collection_stats(grp_by_id_and_a_f_size_q)


def get_dl_ds_collection_stats_with_dups(base_cte: CTE) -> ScalarSelect:
    """
    Get the stats of the subset of the collection of datasets that contains only
    of Datalad datasets, considering individual repos as a dataset regardless of
    the value of `ds_id`.

    :param base_cte: The base CTE that specified the collection of datasets
                     under consideration
    :return: The scalar selectable for obtaining the stats

    Note: The execution of this function requires the Flask app's context
    """

    # Select statement for getting all the Datalad datasets
    dl_ds_q = select(base_cte).filter(base_cte.c.ds_id.is_not(None)).subquery("dl_ds_q")

    return _get_annex_ds_collection_stats(dl_ds_q)


def get_dl_ds_collection_stats(base_cte: CTE) -> ScalarSelect:
    """
    Get the stats of the subset of the collection of datasets that contains only
    of Datalad datasets

    :param base_cte: The base CTE that specified the collection of datasets
        under consideration
    :return: The scalar selectable for obtaining the stats

    Note: The execution of this function requires the Flask app's context
    """

    return select(
        func.jsonb_build_object(
            "unique_ds_stats",
            get_unique_dl_ds_collection_stats(base_cte),
            "stats",
            get_dl_ds_collection_stats_with_dups(base_cte),
        ).label("datalad_ds_collection_stats")
    ).scalar_subquery()


def get_pure_annex_ds_collection_stats(base_cte: CTE) -> ScalarSelect:
    """
    Get the stats of the subset of the collection of datasets that contains only
    of pure annex datasets, the annex datasets that are not Datalad datasets

    :param base_cte: The base CTE that specified the collection of datasets
                     under consideration
    :return: The scalar selectable for obtaining the stats

    Note: The execution of this function requires the Flask app's context
    """
    # Select statement for getting all the pure annex datasets
    pure_annex_ds_q = (
        select(base_cte)
        .filter(
            and_(base_cte.c.branches.has_key("git-annex"), base_cte.c.ds_id.is_(None))
        )
        .subquery("pure_annex_ds_q")
    )

    return _get_annex_ds_collection_stats(pure_annex_ds_q)


def get_non_annex_ds_collection_stats(base_cte: CTE) -> ScalarSelect:
    """
    Get the stats of the subset of the collection of datasets that contains only
    of non-annex datasets

    :param base_cte: The base CTE that specified the collection of datasets
        under consideration
    :return: The scalar selectable for obtaining the stats

    Note: The execution of this function requires the Flask app's context
    """
    # Select statement for getting all the non-annex datasets
    non_annex_ds_q = (
        select(base_cte)
        .filter(not_(base_cte.c.branches.has_key("git-annex")))
        .subquery("non_annex_ds_q")
    )

    return (
        select(
            func.jsonb_build_object("ds_count", func.count()).label(
                "non_annex_ds_collection_stats"
            )
        )
        .select_from(non_annex_ds_q)
        .scalar_subquery()
    )


def get_collection_stats(select_stmt: Select) -> CollectionStats:
    """
    Get the statistics of the collection of dataset URLs specified by the given select
    statement

    :param select_stmt: The given select statement
    :return: The statistics of the collection of dataset URLs

    Note: The execution of this function requires the Flask app's context
    """

    base_cte = select_stmt.cte("base_cte")

    datalad_ds_stats_scalar_subq = get_dl_ds_collection_stats(base_cte)

    # Total number of datasets, as individual repos, without any deduplication
    ds_count_scalar_subq = select(func.count()).select_from(base_cte).scalar_subquery()

    return CollectionStats.parse_obj(
        db.session.execute(
            select(
                func.jsonb_build_object(
                    "datalad_ds_stats",
                    datalad_ds_stats_scalar_subq,
                    "pure_annex_ds_stats",
                    get_pure_annex_ds_collection_stats(base_cte),
                    "non_annex_ds_stats",
                    get_non_annex_ds_collection_stats(base_cte),
                    "summary",
                    func.jsonb_build_object(
                        "unique_ds_count",
                        func.jsonb_extract_path(
                            datalad_ds_stats_scalar_subq, "unique_ds_stats", "ds_count"
                        ),
                        "ds_count",
                        ds_count_scalar_subq,
                    ),
                ).label("collection_stats")
            )
        ).scalar_one()
    )
