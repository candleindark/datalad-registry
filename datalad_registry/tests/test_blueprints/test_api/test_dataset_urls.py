from typing import Optional

import pytest
from pytest_mock import MockerFixture
from yarl import URL as YURL

from datalad_registry.blueprints.api.dataset_urls import DatasetURLRespModel
from datalad_registry.blueprints.api.dataset_urls.models import (
    DEFAULT_PAGE,
    AnnexDsCollectionStats,
    CollectionStats,
    DataladDsCollectionStats,
    DatasetURLPage,
    MetadataReturnOption,
    NonAnnexDsCollectionStats,
    StatsSummary,
)
from datalad_registry.blueprints.api.url_metadata.models import (
    URLMetadataModel,
    URLMetadataRef,
)
from datalad_registry.conf import OperationMode
from datalad_registry.models import RepoUrl
from datalad_registry.tests.tools import populate_with_dataset_urls


class TestDeclareDatasetURL:
    def test_without_body(self, flask_client):
        resp = flask_client.post("/api/v2/dataset-urls")
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "request_json_body",
        [
            {},
            {"abc": "https://example.com"},
            {"url": ""},
            {"url": "hehe"},
            {"url": "haha/hehe"},
            {"url": "www.example.com"},
        ],
    )
    def test_invalid_body(self, flask_client, request_json_body):
        resp = flask_client.post("/api/v2/dataset-urls", json=request_json_body)
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "request_json_body",
        [{"url": "https://example.com"}, {"url": "/hehe"}, {"url": "/haha/hehe"}],
    )
    def test_valid_body(self, flask_client, request_json_body):
        resp = flask_client.post("/api/v2/dataset-urls", json=request_json_body)
        assert resp.status_code == 201

        # Ensure the response body is valid
        DatasetURLRespModel.parse_raw(resp.text)

    def test_retrieve_blocking_record(self, flask_client, monkeypatch):
        """
        Test the case that a submitted URL cannot be inserted into the database
        because there is a blocking record in the database.
        """
        from psycopg2.errors import UniqueViolation
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.scoping import scoped_session

        from datalad_registry.models import RepoUrl

        def mock_commit(_scoped_session_obj):
            raise IntegrityError(None, None, UniqueViolation(None, None, None))

        def mock_rollback(scoped_session_obj):
            original_rollback(scoped_session_obj)

            # Insure a `RepoUrl` record with the given URL
            scoped_session_obj.add(RepoUrl(url=url_as_str))
            original_commit(scoped_session_obj)

        original_commit = scoped_session.commit
        original_rollback = scoped_session.rollback
        url_as_str = "https://www.example.com"

        monkeypatch.setattr(scoped_session, "commit", mock_commit)
        monkeypatch.setattr(scoped_session, "rollback", mock_rollback)

        resp = flask_client.post("/api/v2/dataset-urls", json={"url": url_as_str})

        assert resp.status_code == 201

    def test_failure_to_insert_url_to_db(self, flask_client, monkeypatch):
        """
        Test the case that a submitted URL cannot be inserted into the database
        because concurrent requests and processes repeatedly insert and delete
        `RepoUrl` objects presenting the same URL.
        """
        from psycopg2.errors import UniqueViolation
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.scoping import scoped_session

        def mock_commit(_scoped_session_obj):
            raise IntegrityError(None, None, UniqueViolation(None, None, None))

        monkeypatch.setattr(scoped_session, "commit", mock_commit)

        with pytest.raises(RuntimeError, match="Failed to add the URL"):
            flask_client.post(
                "/api/v2/dataset-urls", json={"url": "https://www.example.com"}
            )

    def test_other_integrity_error(self, flask_client, monkeypatch):
        """
        Test the case that a submitted URL cannot be inserted into the database
        because of an integrity error that is not caused directly by
        a `UniqueViolation` error.
        """
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.orm.scoping import scoped_session

        def mock_commit(_scoped_session_obj):
            raise IntegrityError("This is a test", None, ValueError())

        monkeypatch.setattr(scoped_session, "commit", mock_commit)

        with pytest.raises(IntegrityError, match="This is a test"):
            flask_client.post(
                "/api/v2/dataset-urls", json={"url": "https://www.example.com"}
            )

    @pytest.mark.usefixtures("populate_with_std_ds_urls")
    @pytest.mark.parametrize(
        "url, expected_mark_for_chk_delay_args",
        [
            ("https://www.example.com", None),
            ("http://www.datalad.org", (2,)),
            ("https://handbook.datalad.org", None),
            ("https://www.dandiarchive.org", None),
        ],
    )
    def test_resubmission(
        self,
        url,
        expected_mark_for_chk_delay_args,
        flask_client,
        mocker: MockerFixture,
    ):
        """
        Test resubmitting URLs that already exist in the database
        """

        from datalad_registry.blueprints.api.dataset_urls import mark_for_chk

        mark_for_chk_delay_mock = mocker.patch.object(mark_for_chk, "delay")

        resp = flask_client.post("/api/v2/dataset-urls", json={"url": url})
        assert resp.status_code == 202

        # Ensure the response body is valid
        DatasetURLRespModel.parse_raw(resp.text)

        if expected_mark_for_chk_delay_args is None:
            mark_for_chk_delay_mock.assert_not_called()
        else:
            mark_for_chk_delay_mock.assert_called_once_with(
                *expected_mark_for_chk_delay_args
            )

    def test_read_only_mode(self, flask_app, flask_client, monkeypatch):
        """
        Test that the endpoint is disabled in read-only mode
        """

        monkeypatch.setitem(
            flask_app.config, "DATALAD_REGISTRY_OPERATION_MODE", OperationMode.READ_ONLY
        )

        resp = flask_client.post(
            "/api/v2/dataset-urls", json={"url": "https://www.example.com"}
        )
        assert resp.status_code == 405
        assert set(resp.headers["Allow"].split(", ")) == {"GET", "HEAD", "OPTIONS"}


class TestDatasetURLs:
    @pytest.mark.parametrize(
        "query_params",
        [
            {"url": "www.example.com"},
            {"ds_id": "34"},
            {"min_annex_key_count": "ab"},
            {"max_annex_key_count": "bc"},
            {"min_annexed_files_in_wt_count": "cd"},
            {"max_annexed_files_in_wt_count": "def"},
            {"min_annexed_files_in_wt_size": "efg"},
            {"max_annexed_files_in_wt_size": "hij"},
            {"earliest_last_update": "jkl"},
            {"latest_last_update": "klm"},
            {"min_git_objects_kb": "lmn"},
            {"max_git_objects_kb": "mno"},
            {"processed": "nop"},
            {"return_metadata": "all"},
            {"page": 0},
            {"page": -1},
            {"page": -100},
            {"page": "a"},
            {"per_page": 0},
            {"per_page": -1},
            {"per_page": -100},
            {"per_page": "b"},
            {"order_by": "abc"},
            {"order_dir": "def"},
            {"search": ""},
            {"search": "    "},
            {"search": "   \t \n"},
            {"search": "\n"},
            {"search": "\t  "},
            {"max_annex_key_count": 2, "search": ""},
            {"max_annex_key_count": 2, "search": "    "},
            {"max_annex_key_count": 2, "search": "  \t  "},
            {"max_annex_key_count": 2, "search": "  \t  \n  "},
        ],
    )
    def test_invalid_query_params(self, flask_client, query_params):
        resp = flask_client.get("/api/v2/dataset-urls", query_string=query_params)
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        "query_params",
        [
            {"url": "https://www.example.com"},
            {"ds_id": "2a0b7b7b-a984-4c4a-844c-be3132291d7b"},
            {"min_annex_key_count": "1"},
            {"max_annex_key_count": 2},
            {"min_annexed_files_in_wt_count": 200},
            {"max_annexed_files_in_wt_count": "40"},
            {"min_annexed_files_in_wt_size": 33},
            {"max_annexed_files_in_wt_size": 21},
            {"earliest_last_update": 656409661000},
            {"latest_last_update": "2001-03-22T01:22:34"},
            {"min_git_objects_kb": 40},
            {"max_git_objects_kb": "100"},
            {"processed": True},
            {"return_metadata": None},
            {"return_metadata": MetadataReturnOption.reference.value},
            {"return_metadata": MetadataReturnOption.content.value},
            {"page": 1},
            {"per_page": 10},
            {"per_page": 100},
            {"order_by": "url"},
            {"order_by": "annex_key_count"},
            {"order_by": "annexed_files_in_wt_count"},
            {"order_by": "annexed_files_in_wt_size"},
            {"order_by": "last_update_dt"},
            {"order_by": "git_objects_kb"},
            {"order_dir": "asc"},
            {"order_dir": "desc"},
            {"min_annexed_files_in_wt_size": 33, "search": "   a b c "},
            {"min_annexed_files_in_wt_size": 33, "search": "   a \t b \n c "},
            {"min_annexed_files_in_wt_size": 33, "search": "a"},
        ],
    )
    def test_valid_query_params(self, flask_client, query_params):
        resp = flask_client.get("/api/v2/dataset-urls", query_string=query_params)
        assert resp.status_code == 200

    @pytest.mark.usefixtures("populate_with_std_ds_urls")
    @pytest.mark.parametrize(
        "query_params, expected_output",
        [
            (
                {},
                {
                    "https://www.example.com",
                    "http://www.datalad.org",
                    "https://handbook.datalad.org",
                    "https://www.dandiarchive.org",
                },
            ),
            ({"url": "https://www.example.com"}, {"https://www.example.com"}),
            (
                {"ds_id": "2a0b7b7b-a984-4c4a-844c-be3132291d7c"},
                {"http://www.datalad.org"},
            ),
            (
                {"min_annex_key_count": "39"},
                {"http://www.datalad.org", "https://handbook.datalad.org"},
            ),
            (
                {"min_annex_key_count": "39", "max_annex_key_count": 40},
                {"http://www.datalad.org"},
            ),
            (
                {
                    "min_annexed_files_in_wt_count": 190,
                    "max_annexed_files_in_wt_count": 500,
                },
                {"https://www.example.com", "https://handbook.datalad.org"},
            ),
            ({"min_annexed_files_in_wt_size": 1000_001}, set()),
            ({"max_annexed_files_in_wt_size": 500}, {"http://www.datalad.org"}),
            (
                {"max_annexed_files_in_wt_size": 2000},
                {"https://www.example.com", "http://www.datalad.org"},
            ),
            (
                {
                    "min_annexed_files_in_wt_size": 300,
                    "max_annexed_files_in_wt_size": 2200,
                },
                {"https://www.example.com", "http://www.datalad.org"},
            ),
            (
                {"earliest_last_update": "2001-03-22T01:22:34"},
                {
                    "https://www.example.com",
                    "http://www.datalad.org",
                    "https://handbook.datalad.org",
                },
            ),
            (
                {
                    "earliest_last_update": "2007-03-22T01:22:34",
                    "latest_last_update": "2009-03-22T01:22:34",
                },
                {"https://www.example.com"},
            ),
            (
                {"min_git_objects_kb": 1000, "max_git_objects_kb": 2000},
                {"http://www.datalad.org"},
            ),
            (
                {"processed": True},
                {
                    "https://www.example.com",
                    "http://www.datalad.org",
                    "https://handbook.datalad.org",
                },
            ),
            ({"processed": False}, {"https://www.dandiarchive.org"}),
            (
                {"min_annex_key_count": "39", "max_annexed_files_in_wt_size": 2200},
                {"http://www.datalad.org"},
            ),
            # === filtered by cache_path ===
            (
                {"cache_path": "8c8/fff/e01f2142d88690d92144b00af0"},
                {"https://www.example.com"},
            ),
            (
                {"cache_path": "8c8/fff/e01f2142d88690d92144b00af0/"},
                {"https://www.example.com"},
            ),
            (
                {"cache_path": "8c8/fff/e01f2142d88690d92144b00af0//"},
                {"https://www.example.com"},
            ),
            (
                {"cache_path": "/a/c/8c8/fff/e01f2142d88690d92144b00af0"},
                {"https://www.example.com"},
            ),
            (
                {"cache_path": "/8c8/fff/e01f2142d88690d92144b00af0"},
                {"https://www.example.com"},
            ),
            (
                {"cache_path": "a/c/8c8/fff/e01f2142d88690d92144b00af0"},
                set(),
            ),
            (
                {"cache_path": "72e/4e5/4184da47e282c02ae7e568ba74"},
                {"https://handbook.datalad.org"},
            ),
            (
                {"cache_path": "a/b/c"},
                {"https://www.dandiarchive.org"},
            ),
            # === filtered by search ===
            (
                {"search": "Handbook"},
                {"https://handbook.datalad.org"},
            ),
            (
                {"search": "ds_id:be3132291d7b"},
                {"https://www.example.com"},
            ),
            (
                {"search": "ds_id:be3132291d7c OR dandiarchive"},
                {"http://www.datalad.org", "https://www.dandiarchive.org"},
            ),
            # === filtered by search and other query params ===
            (
                {"search": "ds_id:2a0b7b7b", "min_annex_key_count": "39"},
                {"http://www.datalad.org", "https://handbook.datalad.org"},
            ),
            (
                {"search": "url:.org", "max_annexed_files_in_wt_size": 401},
                {"http://www.datalad.org"},
            ),
        ],
    )
    def test_filter(self, flask_client, query_params, expected_output):
        expected_out_count = len(expected_output)

        resp = flask_client.get("/api/v2/dataset-urls", query_string=query_params)
        assert resp.status_code == 200

        ds_url_page = DatasetURLPage.parse_raw(resp.text)

        assert ds_url_page.cur_pg_num == DEFAULT_PAGE
        assert ds_url_page.prev_pg is None
        assert ds_url_page.next_pg is None
        assert YURL(ds_url_page.first_pg).query["page"] == "1"
        assert YURL(ds_url_page.last_pg).query["page"] == "1"
        assert ds_url_page.collection_stats.summary.ds_count == expected_out_count

        # Check the collection of dataset URLs
        assert {i.url for i in ds_url_page.dataset_urls} == expected_output

    @pytest.mark.usefixtures("populate_with_std_ds_urls")
    @pytest.mark.parametrize(
        "query_params",
        [
            {"search": "unknown_field:example"},
            {"search": "url:example OR no_body:knows"},
            {"url": "https://www.example.com", "search": "never:encountered"},
        ],
    )
    def test_filter_with_invalid_search_query_param(self, query_params, flask_client):
        """
        Test filtering with a search query parameter with invalid grammar/syntax
        """
        resp = flask_client.get("/api/v2/dataset-urls", query_string=query_params)
        assert resp.status_code == 400
        assert "Grammar" in resp.json["description"]

    def test_filter_with_invalid_search_query_param_with_mock(
        self, monkeypatch, flask_client
    ):
        """
        Test handling of the situation where the search query parameter given to the
        endpoint causes a `lark.exceptions.UnexpectedInput` to be raised.
        """
        from lark.exceptions import UnexpectedInput

        from datalad_registry.blueprints.api import dataset_urls

        def mock_parse_query(_query):
            raise UnexpectedInput("Mock UnexpectedInput")

        monkeypatch.setattr(dataset_urls, "parse_query", mock_parse_query)

        resp = flask_client.get("/api/v2/dataset-urls", query_string={"search": "foo"})
        assert resp.status_code == 400
        assert resp.json["description"] == "Invalid search string: Mock UnexpectedInput"

    @pytest.mark.usefixtures("populate_with_url_metadata")
    @pytest.mark.parametrize(
        "metadata_ret_opt",
        [
            None,
            MetadataReturnOption.reference,
            MetadataReturnOption.content,
        ],
    )
    def test_metadata_return(self, metadata_ret_opt, flask_client):
        """
        Test the return of metadata as a part of the returned list of dataset urls
        """
        if metadata_ret_opt is None:
            query_string = {}
        else:
            query_string = {"return_metadata": metadata_ret_opt.value}

        resp = flask_client.get("/api/v2/dataset-urls", query_string=query_string)

        assert resp.status_code == 200

        resp_json = resp.json
        ds_url_pg = DatasetURLPage.parse_obj(resp_json)

        if metadata_ret_opt is None:
            # === metadata is not returned ===

            assert all("metadata" not in url for url in resp_json["dataset_urls"])
        else:
            # === metadata is returned ===

            if metadata_ret_opt is MetadataReturnOption.reference:
                metadata_ret_type = URLMetadataRef
            else:
                metadata_ret_type = URLMetadataModel

            for url in ds_url_pg.dataset_urls:
                assert type(url.metadata) is list

                if url.id == 1:
                    assert len(url.metadata) == 2
                elif url.id == 3:
                    assert len(url.metadata) == 1
                else:
                    assert len(url.metadata) == 0

                assert all(type(m) is metadata_ret_type for m in url.metadata)

    def test_pagination(self, populate_with_std_ds_urls, flask_client):
        """
        Test the pagination of the results
        """

        # For storing all URLs obtained from all pages
        ds_urls: set[str] = set()

        # Get the first page
        resp = flask_client.get("/api/v2/dataset-urls", query_string={"per_page": 2})

        assert resp.status_code == 200

        resp_json = resp.json
        ds_url_pg = DatasetURLPage.parse_obj(resp_json)

        assert ds_url_pg.cur_pg_num == 1
        assert "prev_pg" not in resp_json
        assert ds_url_pg.prev_pg is None
        assert ds_url_pg.next_pg is not None
        assert ds_url_pg.collection_stats.summary.ds_count == 4

        next_pg_lk, first_pg_lk, last_pg_lk = (
            YURL(pg)
            for pg in (ds_url_pg.next_pg, ds_url_pg.first_pg, ds_url_pg.last_pg)
        )

        # Check page links
        assert next_pg_lk.query["page"] == "2"
        # noinspection DuplicatedCode
        assert first_pg_lk.query["page"] == "1"
        assert last_pg_lk.query["page"] == "2"
        for pg_lk in (next_pg_lk, first_pg_lk, last_pg_lk):
            assert pg_lk.path == "/api/v2/dataset-urls"

            assert len(pg_lk.query) == 4
            assert pg_lk.query["per_page"] == "2"
            assert pg_lk.query["order_by"] == "last_update_dt"
            assert pg_lk.query["order_dir"] == "desc"

        assert len(ds_url_pg.dataset_urls) == 2

        # Gather Dataset URLs from the first page
        for url in ds_url_pg.dataset_urls:
            ds_urls.add(str(url.url))

        # Get the second page
        resp = flask_client.get(ds_url_pg.next_pg)

        assert resp.status_code == 200

        resp_json = resp.json
        ds_url_pg = DatasetURLPage.parse_obj(resp_json)

        assert ds_url_pg.cur_pg_num == 2
        assert ds_url_pg.prev_pg is not None
        assert "next_pg" not in resp_json
        assert ds_url_pg.next_pg is None
        assert ds_url_pg.collection_stats.summary.ds_count == 4

        prev_pg_lk, first_pg_lk, last_pg_lk = (
            YURL(pg)
            for pg in (ds_url_pg.prev_pg, ds_url_pg.first_pg, ds_url_pg.last_pg)
        )

        # Check page links
        assert prev_pg_lk.query["page"] == "1"
        # noinspection DuplicatedCode
        assert first_pg_lk.query["page"] == "1"
        assert last_pg_lk.query["page"] == "2"
        for pg_lk in (prev_pg_lk, first_pg_lk, last_pg_lk):
            assert pg_lk.path == "/api/v2/dataset-urls"

            assert len(pg_lk.query) == 4
            assert pg_lk.query["per_page"] == "2"
            assert pg_lk.query["order_by"] == "last_update_dt"
            assert pg_lk.query["order_dir"] == "desc"

        assert len(ds_url_pg.dataset_urls) == 2

        # Gather Dataset URLs from the second page
        for url in ds_url_pg.dataset_urls:
            ds_urls.add(str(url.url))

        assert ds_urls == set(populate_with_std_ds_urls)

    @pytest.mark.usefixtures("populate_with_std_ds_urls")
    @pytest.mark.parametrize(
        "query_params, expected_results_by_id_prefix",
        [
            (
                {
                    "order_by": "url",
                    "order_dir": "asc",
                    "per_page": 2,
                },
                [2, 3, 4, 1],
            ),
            (
                {
                    "order_by": "url",
                    "order_dir": "asc",
                    "per_page": 1,
                },
                [2, 3, 4, 1],
            ),
            (
                {
                    "per_page": 3,
                },
                [2, 1, 3, 4],
            ),
            (
                {
                    "order_by": "git_objects_kb",
                    "order_dir": "desc",
                    "per_page": 1,
                },
                [3, 2, 1, 4],
            ),
            (
                {
                    "order_by": "git_objects_kb",
                    "per_page": 1,
                },
                [3, 2, 1, 4],
            ),
            (
                {
                    "order_by": "annex_key_count",
                    "order_dir": "asc",
                    "per_page": 3,
                },
                [1, 2, 3, 4],
            ),
            (
                {
                    "order_by": "annex_key_count",
                    "order_dir": "asc",
                },
                [1, 2, 3, 4],
            ),
        ],
    )
    def test_ordering(self, query_params, expected_results_by_id_prefix, flask_client):
        """
        Test the ordering of the results
        """
        next_pg: Optional[str] = None
        results_by_id = []

        while True:
            if next_pg is None:
                # Get the first page

                resp = flask_client.get(
                    "/api/v2/dataset-urls", query_string=query_params
                )
            else:
                # Get a subsequent page

                resp = flask_client.get(next_pg)

            assert resp.status_code == 200

            ds_url_pg = DatasetURLPage.parse_raw(resp.text)

            results_by_id.extend(url.id for url in ds_url_pg.dataset_urls)

            if ds_url_pg.next_pg is not None:
                # === There is a subsequent page ===
                next_pg = ds_url_pg.next_pg
            else:
                # === There is no subsequent page ===
                break

        assert (
            results_by_id[: len(expected_results_by_id_prefix)]
            == expected_results_by_id_prefix
        )

    @pytest.mark.parametrize(
        "query_params, expected_stats",
        [
            (
                {},
                CollectionStats(
                    datalad_ds_stats=DataladDsCollectionStats(
                        unique_ds_stats=AnnexDsCollectionStats(
                            ds_count=3,
                            annexed_files_size=400 + 1001,
                            annexed_file_count=50 + 100 + 150,
                        ),
                        stats=AnnexDsCollectionStats(
                            ds_count=6,
                            annexed_files_size=1000 + 1001 + 400,
                            annexed_file_count=120 + 50 + 100 + 120 + 150 + 130,
                        ),
                    ),
                    pure_annex_ds_stats=AnnexDsCollectionStats(
                        ds_count=1, annexed_files_size=600, annexed_file_count=100
                    ),
                    non_annex_ds_stats=NonAnnexDsCollectionStats(ds_count=1),
                    summary=StatsSummary(unique_ds_count=3, ds_count=9),
                ),
            ),
            (
                {"search": "url:datalad"},
                CollectionStats(
                    datalad_ds_stats=DataladDsCollectionStats(
                        unique_ds_stats=AnnexDsCollectionStats(
                            ds_count=2,
                            annexed_files_size=1000 + 400,
                            annexed_file_count=120 + 50,
                        ),
                        stats=AnnexDsCollectionStats(
                            ds_count=2,
                            annexed_files_size=1000 + 400,
                            annexed_file_count=120 + 50,
                        ),
                    ),
                    pure_annex_ds_stats=AnnexDsCollectionStats(
                        ds_count=0, annexed_files_size=None, annexed_file_count=None
                    ),
                    non_annex_ds_stats=NonAnnexDsCollectionStats(ds_count=0),
                    summary=StatsSummary(unique_ds_count=2, ds_count=2),
                ),
            ),
            (
                {"search": "url:.org"},
                CollectionStats(
                    datalad_ds_stats=DataladDsCollectionStats(
                        unique_ds_stats=AnnexDsCollectionStats(
                            ds_count=2,
                            annexed_files_size=1000 + 400,
                            annexed_file_count=120 + 50,
                        ),
                        stats=AnnexDsCollectionStats(
                            ds_count=2,
                            annexed_files_size=1000 + 400,
                            annexed_file_count=120 + 50,
                        ),
                    ),
                    pure_annex_ds_stats=AnnexDsCollectionStats(
                        ds_count=0, annexed_files_size=None, annexed_file_count=None
                    ),
                    non_annex_ds_stats=NonAnnexDsCollectionStats(ds_count=1),
                    summary=StatsSummary(unique_ds_count=2, ds_count=4),
                ),
            ),
            (
                # === The case of an empty set of dataset URLs returned ===
                {"search": "url:.tv"},
                CollectionStats(
                    datalad_ds_stats=DataladDsCollectionStats(
                        unique_ds_stats=AnnexDsCollectionStats(
                            ds_count=0,
                            annexed_files_size=None,
                            annexed_file_count=None,
                        ),
                        stats=AnnexDsCollectionStats(
                            ds_count=0,
                            annexed_files_size=None,
                            annexed_file_count=None,
                        ),
                    ),
                    pure_annex_ds_stats=AnnexDsCollectionStats(
                        ds_count=0, annexed_files_size=None, annexed_file_count=None
                    ),
                    non_annex_ds_stats=NonAnnexDsCollectionStats(ds_count=0),
                    summary=StatsSummary(unique_ds_count=0, ds_count=0),
                ),
            ),
            (
                {"search": "url:distribits.live"},
                CollectionStats(
                    datalad_ds_stats=DataladDsCollectionStats(
                        unique_ds_stats=AnnexDsCollectionStats(
                            ds_count=2,
                            annexed_files_size=1001,
                            annexed_file_count=100 + 150,
                        ),
                        stats=AnnexDsCollectionStats(
                            ds_count=4,
                            annexed_files_size=1001,
                            annexed_file_count=100 + 120 + 150 + 130,
                        ),
                    ),
                    pure_annex_ds_stats=AnnexDsCollectionStats(
                        ds_count=0, annexed_files_size=None, annexed_file_count=None
                    ),
                    non_annex_ds_stats=NonAnnexDsCollectionStats(ds_count=0),
                    summary=StatsSummary(unique_ds_count=2, ds_count=4),
                ),
            ),
        ],
    )
    def test_stats(self, query_params, expected_stats, flask_app, flask_client):
        """
        Test the compilation of stats regarding the returned dataset URLs
        """

        # Populate the DB with dataset URLs suitable for testing the stats
        urls = [
            RepoUrl(
                url="https://www.example.com",
                ds_id=None,
                annexed_files_in_wt_count=100,
                annexed_files_in_wt_size=600,
                branches={
                    "git-annex": {
                        "hexsha": "f21cff198ce84438bd60d459577401d7168fd6db",
                        "last_commit_dt": "2022-11-18T19:18:23+00:00",
                    }
                },
            ),
            RepoUrl(
                url="http://www.datalad.org",
                ds_id="2a0b7b7b-a984-4c4a-844c-be3132291a7c",
                annexed_files_in_wt_count=120,
                annexed_files_in_wt_size=1000,
                branches={
                    "git-annex": {
                        "hexsha": "f21cff198ce84438bd60d459577401d7168fd6ta",
                        "last_commit_dt": "2022-11-18T19:18:23+00:00",
                    }
                },
            ),
            RepoUrl(
                url="https://handbook.datalad.org",
                ds_id="2b73b99e-59cc-4f35-833a-69c75ca5b0c5",
                annexed_files_in_wt_count=50,
                annexed_files_in_wt_size=400,
                branches={
                    "git-annex": {
                        "hexsha": "f21cff198ce84438bd60d459577401d7168fd6cc",
                        "last_commit_dt": "2022-11-18T19:18:23+00:00",
                    }
                },
            ),
            RepoUrl(
                url="https://www.dandiarchive.org",
                ds_id=None,
                annexed_files_in_wt_count=100,
                annexed_files_in_wt_size=300,
            ),
            RepoUrl(
                url="https://distribits.live",
                ds_id="2a0b7b7b-a984-4c4a-844c-be3132291a7c",
                annexed_files_in_wt_count=100,
                annexed_files_in_wt_size=1001,
                branches={
                    "git-annex": {
                        "hexsha": "f21cff198ce84438bd60d459577401d7168fdaba",
                        "last_commit_dt": "2022-11-18T19:18:23+00:00",
                    }
                },
            ),
            RepoUrl(
                url="https://distribits.live/1",
                ds_id="48185fb3-aa80-47b4-8ab1-1d7d9fc8b192",
                annexed_files_in_wt_count=120,
                annexed_files_in_wt_size=None,
                branches={
                    "git-annex": {
                        "hexsha": "f21cff198ce84438bd60d459577401d7168fdaba",
                        "last_commit_dt": "2022-11-18T19:18:23+00:00",
                    }
                },
            ),
            RepoUrl(
                url="https://distribits.live/2",
                ds_id="48185fb3-aa80-47b4-8ab1-1d7d9fc8b192",
                annexed_files_in_wt_count=150,
                annexed_files_in_wt_size=None,
                branches={
                    "git-annex": {
                        "hexsha": "f21cff198ce84438bd60d459577401d7168fdaba",
                        "last_commit_dt": "2022-11-18T19:18:23+00:00",
                    }
                },
            ),
            RepoUrl(
                url="https://distribits.live/3",
                ds_id="48185fb3-aa80-47b4-8ab1-1d7d9fc8b192",
                annexed_files_in_wt_count=130,
                annexed_files_in_wt_size=None,
                branches={
                    "git-annex": {
                        "hexsha": "f21cff198ce84438bd60d459577401d7168fdaba",
                        "last_commit_dt": "2022-11-18T19:18:23+00:00",
                    }
                },
            ),
            RepoUrl(
                url="https://centerforopenneuroscience.org",
                ds_id=None,
                annexed_files_in_wt_count=None,
                annexed_files_in_wt_size=None,
                branches={
                    "main": {
                        "hexsha": "f21cff198ce84438bd60d459577401d7168fdaba",
                        "last_commit_dt": "2022-11-18T19:18:23+00:00",
                    },
                    "dev": {
                        "hexsha": "f21cff198ce84438bd60d459577401d7175fdaba",
                        "last_commit_dt": "2022-11-18T19:18:23+00:00",
                    },
                },
            ),
        ]
        populate_with_dataset_urls(urls, flask_app)

        resp = flask_client.get("/api/v2/dataset-urls", query_string=query_params)

        assert DatasetURLPage.parse_raw(resp.text).collection_stats == expected_stats


@pytest.mark.usefixtures("populate_with_2_dataset_urls")
class TestDatasetURL:
    @pytest.mark.parametrize("dataset_url_id", [-100, -1, 0, 2, 60, 71, 100])
    def test_invalid_id(self, flask_client, dataset_url_id):
        resp = flask_client.get(f"/api/v2/dataset-urls/{dataset_url_id}")
        assert resp.status_code == 404

    @pytest.mark.parametrize(
        "dataset_url_id, url", [(1, "https://example.com"), (3, "/foo/bar")]
    )
    def test_valid_id(self, flask_client, dataset_url_id, url):
        resp = flask_client.get(f"/api/v2/dataset-urls/{dataset_url_id}")
        assert resp.status_code == 200

        # Ensure the response body is valid
        ds_url = DatasetURLRespModel.parse_raw(resp.text)

        # Ensure the correct URL is fetched
        assert str(ds_url.url) == url
