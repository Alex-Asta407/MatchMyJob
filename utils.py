import re

# Utility functions for skill normalization and matching

# Define synonym mappings for skills
SYNONYMS = {
    "js": "javascript",
    "py": "python",
    "c#": "csharp",
    "c++": "cpp",
    "html5": "html",
    "css3": "css",
    # add more as needed
}


def normalize_skill(skill: str) -> str:
    """
    Normalize a single skill string:
    - lowercase
    - strip whitespace
    - map known synonyms
    """
    s = skill.strip().lower()
    # replace non-alphanumeric characters except plus and sharp
    s = re.sub(r"[^a-z0-9#+]+", "", s)
    # map synonyms
    return SYNONYMS.get(s, s)


def normalize_skills(skills: list[str]) -> list[str]:
    """
    Normalize a list of skill strings, remove duplicates, and sort.
    """
    normalized = [normalize_skill(s) for s in skills]
    # remove empties
    normalized = [s for s in normalized if s]
    # deduplicate
    unique = sorted(set(normalized))
    return unique


def match_score(job_skills: list[str], candidate_skills: list[str]) -> float:
    """
    Compute the match score between a job's required skills and candidate skills.
    score = |intersection| / max(1, |job_skills|)
    """
    js = set(normalize_skills(job_skills))
    cs = set(normalize_skills(candidate_skills))
    if not js:
        return 1.0
    return len(js & cs) / len(js)


