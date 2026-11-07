#!/usr/bin/env python3
"""Generate static SVG cards from public GitHub account and repository data."""

from __future__ import annotations

import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
MAX_RESPONSE_BYTES = 2_000_000
MAX_REPOSITORY_PAGES = 20
ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "assets"
LANGUAGE_COLORS = {
    "C": "#555555",
    "C++": "#f34b7d",
    "Go": "#00ADD8",
    "Java": "#b07219",
    "JavaScript": "#f1e05a",
    "Lua": "#000080",
    "Python": "#3572A5",
    "Rust": "#dea584",
    "TypeScript": "#3178c6",
}


def validate_username(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", value):
        raise ValueError("GITHUB_USERNAME must be a valid GitHub username")
    return value


def get_json(path: str, token: str) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-profile-stats-generator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        f"{API_ROOT}{path}",
        headers=headers,
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}") from None
    except (TimeoutError, URLError):
        raise RuntimeError("Unable to reach the GitHub API") from None
    if len(payload) > MAX_RESPONSE_BYTES:
        raise RuntimeError("GitHub API response exceeded the size limit")
    try:
        return json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("GitHub API returned invalid JSON") from None


def nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"GitHub API returned an invalid {field}")
    return value


def fetch_repositories(username: str, token: str) -> list[dict[str, object]]:
    repositories: list[dict[str, object]] = []
    for page in range(1, MAX_REPOSITORY_PAGES + 1):
        query = urlencode({"type": "owner", "per_page": 100, "page": page})
        response = get_json(f"/users/{username}/repos?{query}", token)
        if not isinstance(response, list):
            raise ValueError("GitHub API returned an invalid repository list")
        for repository in response:
            if not isinstance(repository, dict):
                raise ValueError("GitHub API returned an invalid repository record")
            repositories.append(repository)
        if len(response) < 100:
            break
        if page == MAX_REPOSITORY_PAGES:
            raise RuntimeError("Repository list exceeded the configured pagination limit")
    return repositories


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def is_xml_text(value: str) -> bool:
    return all(
        char in "\t\n\r"
        or 0x20 <= ord(char) <= 0xD7FF
        or 0xE000 <= ord(char) <= 0xFFFD
        or 0x10000 <= ord(char) <= 0x10FFFF
        for char in value
    )


def write_stats_card(followers: int, public_repositories: int, stars: int) -> None:
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="500" height="165" viewBox="0 0 500 165" role="img" aria-labelledby="title desc">
<title id="title">GitHub public stats for walterfan</title>
<desc id="desc">Followers, public repositories, and stars across non-fork public repositories.</desc>
<rect x="1" y="1" width="498" height="163" rx="8" fill="#fff" stroke="#d0d7de"/>
<text x="24" y="34" font-family="Arial,sans-serif" font-size="18" font-weight="600" fill="#1f2328">GitHub Public Stats</text>
<g font-family="Arial,sans-serif" text-anchor="middle">
  <text x="100" y="78" font-size="13" fill="#656d76">Followers</text>
  <text x="100" y="119" font-size="30" font-weight="600" fill="#0969da">{followers:,}</text>
  <text x="250" y="78" font-size="13" fill="#656d76">Public repositories</text>
  <text x="250" y="119" font-size="30" font-weight="600" fill="#0969da">{public_repositories:,}</text>
  <text x="400" y="78" font-size="13" fill="#656d76">Stars</text>
  <text x="400" y="119" font-size="30" font-weight="600" fill="#0969da">{stars:,}</text>
</g>
</svg>
'''
    (ASSET_DIR / "github-stats.svg").write_text(svg, encoding="utf-8")


def write_languages_card(language_counts: dict[str, int]) -> None:
    entries = sorted(language_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    total = sum(language_counts.values())
    rows: list[str] = []
    for index, (language, count) in enumerate(entries):
        y = 67 + index * 19
        percentage = round(count * 100 / total) if total else 0
        bar_width = round(200 * count / max((entry[1] for entry in entries), default=1))
        color = LANGUAGE_COLORS.get(language, "#8c959f")
        rows.append(
            f'<text x="24" y="{y}" font-family="Arial,sans-serif" font-size="12" fill="#1f2328">{escape(language[:24])}</text>'
            f'<rect x="160" y="{y - 10}" width="200" height="8" rx="4" fill="#eaeef2"/>'
            f'<rect x="160" y="{y - 10}" width="{bar_width}" height="8" rx="4" fill="{color}"/>'
            f'<text x="390" y="{y}" font-family="Arial,sans-serif" font-size="12" text-anchor="end" fill="#656d76">{percentage}%</text>'
        )
    if not rows:
        rows.append('<text x="24" y="80" font-family="Arial,sans-serif" font-size="13" fill="#656d76">No public language data</text>')
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="420" height="165" viewBox="0 0 420 165" role="img" aria-labelledby="title desc">
<title id="title">Top languages by public repository count</title>
<desc id="desc">The five most common primary languages across public, non-fork repositories.</desc>
<rect x="1" y="1" width="418" height="163" rx="8" fill="#fff" stroke="#d0d7de"/>
<text x="24" y="34" font-family="Arial,sans-serif" font-size="18" font-weight="600" fill="#1f2328">Top Languages</text>
''' + "\n".join(rows) + "\n</svg>\n"
    (ASSET_DIR / "top-languages.svg").write_text(svg, encoding="utf-8")


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    username = validate_username(os.environ.get("GITHUB_USERNAME", ""))

    profile = get_json(f"/users/{username}", token)
    if not isinstance(profile, dict):
        raise ValueError("GitHub API returned an invalid profile")
    followers = nonnegative_int(profile.get("followers"), "followers count")
    public_repositories = nonnegative_int(profile.get("public_repos"), "repository count")

    repositories = fetch_repositories(username, token)
    stars = 0
    language_counts: dict[str, int] = {}
    for repository in repositories:
        owner = repository.get("owner")
        if not isinstance(owner, dict) or owner.get("login") != username:
            raise ValueError("GitHub API returned a repository with an unexpected owner")
        if repository.get("fork") is True:
            continue
        stars += nonnegative_int(repository.get("stargazers_count"), "star count")
        language = repository.get("language")
        if language is not None:
            if (
                not isinstance(language, str)
                or len(language) > 100
                or not is_xml_text(language)
            ):
                raise ValueError("GitHub API returned an invalid language name")
            language_counts[language] = language_counts.get(language, 0) + 1

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    write_stats_card(followers, public_repositories, stars)
    write_languages_card(language_counts)
    print("Generated GitHub stats SVG cards.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
