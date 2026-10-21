"""Small response helpers shared by the API tests."""


def results(response):
    assert response.status_code == 200, response.content
    return response.json()["results"]


def keys(response):
    return [row["key"] for row in results(response)]
