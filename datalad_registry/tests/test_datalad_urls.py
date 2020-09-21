import pytest
import subprocess as sp
from unittest.mock import patch

from datalad_registry.utils import url_encode

# ATTN: `client` is a session-level fixture, so the database is shared
# across tests.


def test_token_get(client, dsid):
    url = "doesnt.matter"
    url_encoded = url_encode(url)
    data = client.get(
        f"/v1/datasets/{dsid}/urls/{url_encoded}/token").get_json()
    assert "token" in data
    assert data["dsid"] == dsid
    assert data["ref"] == "refs/datalad-registry/" + data["token"]
    assert data["url"] == url


@pytest.mark.parametrize("bad_url", ["a", "abcd"])
def test_token_bad_url_get(client, dsid, bad_url):
    response = client.get(f"/v1/datasets/{dsid}/urls/{bad_url}/token")
    assert response.status_code == 400


def test_urls_get_empty(client, dsid):
    data = client.get(f"/v1/datasets/{dsid}/urls").get_json()
    assert data["dsid"] == dsid
    assert data["urls"] == []


def test_urls_post_invalid_data(client, dsid):
    response = client.post(f"/v1/datasets/{dsid}/urls", json={})
    assert response.status_code == 400


def test_urls_post_unknown_token(client, dsid):
    response = client.post(f"/v1/datasets/{dsid}/urls",
                           json={"token": "unknown",
                                 "url": "doesnt.matter"})
    assert response.status_code == 400


@pytest.mark.parametrize("bad_url", ["a", "abcd"])
def test_url_bad_url_get(client, dsid, bad_url):
    response = client.get(f"/v1/datasets/{dsid}/urls/{bad_url}")
    assert response.status_code == 400


def test_register_url(client, dsid, tmp_path):
    dset = tmp_path / "ds"
    dset.mkdir()

    url_encoded = url_encode("file:///" + str(dset))

    d_token = client.get(
        f"/v1/datasets/{dsid}/urls/{url_encoded}/token").get_json()

    def get_status():
        response = client.get(
            f"/v1/datasets/{dsid}/urls/{url_encoded}")
        return response.get_json()["status"]

    assert get_status() == "token requested"

    sp.run(["git", "init"], cwd=str(dset))
    sp.run(["git", "commit", "--allow-empty", "-mc0"], cwd=str(dset))
    sp.run(["git", "update-ref", d_token["ref"], "HEAD"], cwd=str(dset))

    r_post = client.post(f"/v1/datasets/{dsid}/urls", json=d_token)
    assert r_post.status_code == 202

    assert get_status() == "known"

    # And again.
    d_token2 = client.get(
        f"/v1/datasets/{dsid}/urls/{url_encoded}/token").get_json()
    r_post2 = client.post(f"/v1/datasets/{dsid}/urls", json=d_token2)
    assert r_post2.status_code == 202
    assert get_status() == "known"


def test_register_url_expired_token(client, dsid, tmp_path):
    dset = tmp_path / "ds"
    dset.mkdir()

    url_encoded = url_encode("file:///" + str(dset))

    d_token = client.get(
        f"/v1/datasets/{dsid}/urls/{url_encoded}/token").get_json()

    with patch("datalad_registry.dataset_urls._TOKEN_TTL", 0):
        r_post = client.post(f"/v1/datasets/{dsid}/urls", json=d_token)
    assert r_post.status_code == 410


def test_register_url_failed_verification(client, dsid, tmp_path):
    url_encoded = url_encode("file:///" + str(tmp_path))

    d_token = client.get(
        f"/v1/datasets/{dsid}/urls/{url_encoded}/token").get_json()
    r_post = client.post(f"/v1/datasets/{dsid}/urls", json=d_token)
    assert r_post.status_code == 202
    data = client.get(f"/v1/datasets/{dsid}/urls/{url_encoded}").get_json()
    assert data["status"] == "verification failed"
