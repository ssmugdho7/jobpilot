"""Keyword-based CV matching — picks the closest uploaded CV for a job posting."""

import re


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text (lowercased)."""
    text = text.lower()
    # Remove common stopwords
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "need", "dare",
        "ought", "used", "this", "that", "these", "those", "i", "me", "my",
        "we", "our", "you", "your", "he", "him", "his", "she", "her", "it",
        "its", "they", "them", "their", "what", "which", "who", "whom",
        "where", "when", "why", "how", "all", "each", "every", "both", "few",
        "more", "most", "other", "some", "such", "no", "nor", "not", "only",
        "own", "same", "so", "than", "too", "very", "just", "about", "above",
        "after", "again", "also", "am", "an", "as", "before", "between",
        "during", "into", "through", "until", "while", "working", "experience",
        "year", "years", "team", "company", "role", "position", "job",
    }
    words = re.findall(r"[a-z][a-z0-9+#.]{1,30}", text)
    return {w for w in words if w not in stopwords and len(w) > 1}


def _skill_overlap_score(job_keywords: set[str], cv_skills: list[str]) -> float:
    """Compute a 0-1 score based on how many CV skills appear in the job text."""
    if not cv_skills:
        return 0.0
    cv_skills_lower = {s.lower().strip() for s in cv_skills if s.strip()}
    if not cv_skills_lower:
        return 0.0

    hits = 0
    for skill in cv_skills_lower:
        # Check if skill (or a significant part) appears in job keywords
        skill_words = set(skill.split())
        if skill in job_keywords or skill_words & job_keywords:
            hits += 1
        else:
            # Partial match: check if any job keyword contains the skill or vice versa
            for kw in job_keywords:
                if len(skill) >= 3 and (skill in kw or kw in skill):
                    hits += 1
                    break

    return hits / max(len(cv_skills_lower), 1)


def _role_match_score(job_text: str, cv_profile: dict) -> float:
    """Score based on how well the CV's summary/experience matches the job role."""
    cv_text = " ".join([
        cv_profile.get("summary") or "",
        cv_profile.get("experience") or "",
    ]).lower()
    if not cv_text.strip():
        return 0.0

    job_kw = _extract_keywords(job_text)
    cv_kw = _extract_keywords(cv_text)

    if not job_kw or not cv_kw:
        return 0.0

    overlap = job_kw & cv_kw
    return len(overlap) / max(len(job_kw), 1)


def find_best_cv(job_text: str, user_cvs: list) -> object:
    """Pick the CV with the highest combined score.

    Scoring: 70% skill overlap + 30% role/keyword match.
    """
    best_cv = None
    best_score = -1.0

    for cv in user_cvs:
        profile = cv.parsed_profile or {}
        skills = profile.get("skills") or []

        skill_score = _skill_overlap_score(_extract_keywords(job_text), skills)
        role_score = _role_match_score(job_text, profile)

        combined = skill_score * 0.7 + role_score * 0.3

        if combined > best_score:
            best_score = combined
            best_cv = cv

    # Fallback: return first CV if no scoring worked
    if best_cv is None and user_cvs:
        best_cv = user_cvs[0]

    return best_cv
