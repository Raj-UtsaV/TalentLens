import os
import re

from .extraction import group_education, normalize_skill


class SemanticMatcher:
    def __init__(self):
        self.model = None
        self.failed = False

    def similarity(self, left: str, right: str) -> float:
        if not left.strip() or not right.strip(): return 0.0
        if not self.failed:
            try:
                from sentence_transformers import SentenceTransformer
                if self.model is None:
                    self.model = SentenceTransformer(os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"))
                a, b = self.model.encode([left, right], normalize_embeddings=True)
                return max(0.0, min(1.0, float(a @ b)))
            except Exception:
                self.failed = True
        # Deterministic low-dependency fallback when model download/runtime is unavailable.
        a, b = set(left.lower().split()), set(right.lower().split())
        return len(a & b) / len(a | b) if a | b else 0.0


semantic_matcher = SemanticMatcher()


def _degree_level(text: str) -> int | None:
    if re.search(r"\b(ph\.?d|doctorate|doctoral)\b", text, re.I): return 5
    if re.search(r"\b(master|m\.?tech|m\.?sc|mba|mca|postgraduate)\b", text, re.I): return 4
    if re.search(r"\b(bachelor|b\.?tech|b\.?e\.?|b\.?sc|bca|undergraduate)\b", text, re.I): return 3
    if re.search(r"\b(intermediate|higher secondary|class\s*xii|12th|grade\s*12)\b", text, re.I): return 2
    if re.search(r"\b(matriculat|secondary school|class\s*x\b|10th|grade\s*10)\b", text, re.I): return 1
    if re.search(r"\b(diploma|associate)\b", text, re.I): return 2
    return None


def _education_field(text: str) -> str | None:
    normalized = text.lower()
    if re.search(r"\b(cse|computer science(?: and engineering)?)\b", normalized): return "computer science"
    if re.search(r"\bcivil(?: engineering)?\b", normalized): return "civil"
    if re.search(r"\b(information technology|\bit\b)\b", normalized): return "information technology"
    if re.search(r"\b(software engineering|software development)\b", normalized): return "software engineering"
    if re.search(r"\b(computer engineering|computer applications)\b", normalized): return "computer engineering"
    if re.search(r"\b(artificial intelligence|machine learning|\bai/ml\b|\bai & ds\b)\b", normalized): return "artificial intelligence"
    if re.search(r"\b(data science|data analytics)\b", normalized): return "data science"
    if re.search(r"\b(electronics|electrical and communication|\bece\b|\beee\b)\b", normalized): return "electronics"
    if re.search(r"\b(information systems|cyber ?security)\b", normalized): return "information systems"
    if re.search(r"\b(computational mathematics|mathematics|mathematical computing|statistics)\b", normalized): return "computational mathematics"
    match = re.search(r"\b(?:major(?:ing)? in|speciali[sz]ation in|in)\s+([a-z][a-z &./-]{2,60})", normalized)
    return re.sub(r"\s+", " ", match.group(1)).strip(" .,-") if match else None


TECH_FIELDS = {"computer science", "information technology", "software engineering", "computer engineering",
               "artificial intelligence", "data science", "electronics", "information systems", "computational mathematics"}


def _related_field(required: str, candidate: str) -> bool:
    return required == candidate or required in TECH_FIELDS and candidate in TECH_FIELDS


def _gpa(text: str) -> tuple[float, float] | None:
    match = re.search(r"(?:cgpa|gpa)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:/\s*(\d+(?:\.\d+)?))?", text, re.I)
    if not match:
        match = re.search(r"(\d+(?:\.\d+)?)(?:\s*/\s*(10|4))?\s*(?:cgpa|gpa)", text, re.I)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2) or 10)


def _education_score(requirements: list[str], education: list[str]) -> float | None:
    if not requirements or not education:
        return None
    required = " ".join(requirements)
    records = group_education(education)
    best = max(records, key=lambda record: _degree_level(" ".join(record["details"])) or 0, default=None)
    candidate = " ".join(best["details"]) if best else " ".join(education)
    parts = []
    required_degree, candidate_degree = _degree_level(required), _degree_level(candidate)
    if required_degree is not None and candidate_degree is not None:
        parts.append((.5, min(100, 100 * candidate_degree / required_degree)))
    required_field, candidate_field = _education_field(required), _education_field(candidate)
    if required_field and candidate_field:
        parts.append((.3, 100 if _related_field(required_field, candidate_field) else 0))
    required_gpa, candidate_gpa = _gpa(required), _gpa(candidate)
    if required_gpa and candidate_gpa:
        req_value, req_scale = required_gpa
        have_value, have_scale = candidate_gpa
        parts.append((.2, min(100, 100 * (have_value / have_scale) / (req_value / req_scale))))
    return sum(weight * value for weight, value in parts) / sum(weight for weight, _ in parts) if parts else None


def score_candidate(job: dict, candidate: dict, weights: dict | None = None, semantic_fn=None) -> dict:
    weights = weights or {"skills": .5, "semantic": .25, "experience": .15, "education": .10}
    total_weight = sum(max(0, float(v)) for v in weights.values())
    if not total_weight: raise ValueError("At least one score weight must be positive")
    required = {normalize_skill(x) for x in job.get("required_skills", [])}
    preferred = {normalize_skill(x) for x in job.get("preferred_skills", [])}
    candidate_skills = {normalize_skill(x) for x in candidate.get("skills", [])}
    matched = sorted(required & candidate_skills)
    missing = sorted(required - candidate_skills)
    skills = (100 * len(matched) / len(required) if required else 0) if not preferred else min(100, 100 * (len(matched) + .5 * len(preferred & candidate_skills)) / max(1, len(required) + .5 * len(preferred)))
    fn = semantic_fn or semantic_matcher.similarity
    semantic = max(0, min(100, 100 * fn(job.get("description", ""), candidate.get("parsed_text", "")))) if job.get("description") and candidate.get("parsed_text") else None
    need = job.get("min_experience")
    have = candidate.get("experience_years")
    experience = min(100, 100 * have / need) if need and have is not None else None
    education = _education_score(job.get("qualifications", []), candidate.get("education", []))
    components = {"skills": skills, "semantic": semantic, "experience": experience, "education": education}
    if not (required or preferred): components["skills"] = None
    applicable = {k: float(v) for k, v in weights.items() if k in components and v > 0 and components[k] is not None}
    denominator = sum(applicable.values())
    overall = sum(components[k] * w for k, w in applicable.items()) / denominator if denominator else 0.0
    not_scored = [k for k, value in components.items() if value is None]
    explanation = f"Matched {len(matched)} of {len(required)} required skills."
    if semantic is not None:
        explanation += f" Semantic fit: {semantic:.0f}%."
    if not_scored:
        explanation += " Not scored (insufficient role or resume data): " + ", ".join(not_scored) + ". Remaining weights were normalized."
    return {"overall_score": round(max(0, min(100, overall)), 2), "scores": {**{k: round(v, 2) if v is not None else None for k, v in components.items()}, "weights": weights},
            "matched_skills": matched, "missing_skills": missing,
            "explanation": explanation}
