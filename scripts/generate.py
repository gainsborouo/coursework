import os
import re
from collections import defaultdict
from typing import Any

import requests


ORG_NAME = os.environ["ORG_NAME"]
TOKEN = os.environ["GITHUB_TOKEN"]

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {TOKEN}",
}

API_URL = f"https://api.github.com/orgs/{ORG_NAME}/repos?type=public&per_page=100"

SCHOOL_PREFIX_MAP = {
    "NYCU_": "NYCU",
    "NEHS_": "NEHS",
}

SEMESTER_PATTERN = re.compile(r"^(\d{3})(上|下)\s+")
SCHOOL_NAME_PATTERN = re.compile(r"^(交大|竹科實中)\s+")


def fetch_repos() -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    url = API_URL

    while url:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        repos.extend(response.json())

        next_url = None
        link_header = response.headers.get("Link")
        if link_header:
            links = requests.utils.parse_header_links(
                link_header.rstrip(">").replace(">,", ",<")
            )
            for link in links:
                if link.get("rel") == "next":
                    next_url = link.get("url")
                    break

        url = next_url

    return repos


def detect_school(repo_name: str) -> str:
    for prefix, school in SCHOOL_PREFIX_MAP.items():
        if repo_name.startswith(prefix):
            return school
    return "Other"


def parse_description(description: str | None) -> tuple[str | None, str]:
    if not description:
        return None, ""

    desc = description.strip()

    semester_match = SEMESTER_PATTERN.match(desc)
    if not semester_match:
        return None, desc

    semester = f"{semester_match.group(1)}{semester_match.group(2)}"
    rest = desc[semester_match.end():].strip()

    rest = SCHOOL_NAME_PATTERN.sub("", rest).strip()

    return semester, rest


def semester_sort_key(semester: str | None) -> tuple[int, int]:
    if not semester:
        return (-1, -1)

    year = int(semester[:-1])
    half = semester[-1]
    half_order = 1 if half == "下" else 0
    return (year, half_order)


def display_title(repo: dict[str, Any]) -> str:
    _, parsed_course_name = parse_description(repo.get("description"))
    return parsed_course_name or repo["name"]


def repo_sort_key(repo: dict[str, Any]) -> tuple[str, str]:
    semester, _ = parse_description(repo.get("description"))
    return (semester or "", display_title(repo).lower())


def build_markdown(repos: list[dict[str, Any]]) -> str:
    grouped: dict[str, dict[str | None, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for repo in repos:
        school = detect_school(repo["name"])
        semester, _ = parse_description(repo.get("description"))
        grouped[school][semester].append(repo)

    school_order = ["NYCU", "NEHS", "Other"]

    parts: list[str] = [
        "<!-- AUTO-GENERATED: DO NOT EDIT -->",
        "# Coursework",
        "",
        "This repository indexes my coursework repositories.",
        "",
    ]

    for school in school_order:
        semesters = grouped.get(school)
        if not semesters:
            continue

        parts.append(f"## {school}")
        parts.append("")

        sorted_semesters = sorted(
            semesters.keys(),
            key=semester_sort_key,
            reverse=True,
        )

        for semester in sorted_semesters:
            repos_in_semester = sorted(semesters[semester], key=repo_sort_key)

            heading = semester if semester else "Uncategorized"
            parts.append(f"### {heading}")
            parts.append("")

            for repo in repos_in_semester:
                title = display_title(repo)
                url = repo["html_url"]
                parts.append(f"- [{title}]({url})")

            parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def main() -> None:
    repos = fetch_repos()

    repos = [repo for repo in repos if not repo.get("private", False)]
    repos = [repo for repo in repos if repo["name"].lower() != "schoolwork"]

    repos = sorted(repos, key=lambda r: r["name"])

    content = build_markdown(repos)

    with open("README.md", "w", encoding="utf-8") as file:
        file.write(content)


if __name__ == "__main__":
    main()