"""Thin GitHub REST helper shared by the sync scripts. Tests patch `ghapi.get`."""

import os

import requests

API = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


def get(path: str, params: dict | None = None, accept: str | None = None) -> requests.Response:
    """GET `path` (relative to the API root, or a full URL). Does not raise on HTTP errors."""
    url = path if path.startswith("http") else f"{API}{path}"
    headers = HEADERS | ({"Accept": accept} if accept else {})
    return requests.get(url, headers=headers, params=params)
