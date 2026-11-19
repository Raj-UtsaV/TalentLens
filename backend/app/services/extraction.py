import re
from datetime import date

SKILL_VOCAB = {
    "python", "java", "javascript", "typescript", "react", "node.js", "fastapi", "django", "flask",
    "sql", "postgresql", "mysql", "mongodb", "aws", "azure", "gcp", "docker", "kubernetes", "git",
    "machine learning", "deep learning", "nlp", "pytorch", "tensorflow", "scikit-learn", "pandas",
    "data analysis", "rest api", "leadership", "communication", "agile", "html", "css", "linux",
    "spark", "airflow", "redis", "c++", "c#", ".net", "ruby", "go", "rust", "power bi", "tableau",
}
ALIASES = {"js": "javascript", "ts": "typescript", "postgres": "postgresql", "k8s": "kubernetes", "ml": "machine learning", "react.js": "react"}
SECTION_NAMES = {
    "summary": "summary", "professional summary": "summary", "profile": "summary",
    "experience": "employment", "work experience": "employment", "professional experience": "employment",
    "employment": "employment", "employment history": "employment", "projects": "projects",
    "project": "projects", "key projects": "projects", "personal projects": "projects", "academic projects": "projects", "education": "education",
    "technical skills": "skills", "skills": "skills", "certifications": "certifications",
    "achievements": "achievements", "awards": "achievements", "leadership": "achievements",
    "extracurricular activities": "achievements", "volunteering": "achievements",
}
_nlp = None
_nlp_checked = False


def normalize_skill(skill: str) -> str:
    key = re.sub(r"\s+", " ", skill.lower().strip())
    return ALIASES.get(key, key)


def matching_text(text: str, name: str | None = None) -> str:
    text = re.sub(r"\[\[URL:.*?\]\]|https?://\S+", " ", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", " ", text)
    text = re.sub(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)", " ", text)
    text = re.sub(r"(?im)^.*\b(?:date of birth|dob|born|age|gender|sex|marital status|religion|nationality|citizenship|disability|pronouns?)\b.*$", " ", text)
    if name:
        text = re.sub(re.escape(name), " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _resume_sections(text: str) -> dict[str, list[str]]:
    headings = sorted(SECTION_NAMES, key=len, reverse=True)
    heading_pattern = "|".join(re.escape(h) for h in headings)
    text = re.sub(r"[•▪●◦]", "\n§TITLE§", text)
    text = re.sub(rf"(?i)(?<!\w)({heading_pattern})\s*(?=[:|\-–—\n])", r"\n\1\n", text)
    sections = {name: [] for name in set(SECTION_NAMES.values())}
    current = "summary"
    for raw in text.splitlines():
        title_marker = raw.lstrip().startswith("§TITLE§")
        detail_bullet = bool(re.match(r"^\s*[-–—]\s*", raw))
        raw = raw.replace("§TITLE§", "", 1) if title_marker else raw
        line = raw.strip(" \t•▪●◦|:-–—")
        if not line:
            continue
        heading = SECTION_NAMES.get(re.sub(r"\s+", " ", line.lower()))
        if heading:
            current = heading
        else:
            if current == "projects":
                if title_marker:
                    line = "\x01" + line
                elif detail_bullet:
                    line = "• " + line
            sections[current].append(line)
    return sections


def group_education(lines: list[str]) -> list[dict]:
    records: list[dict] = []
    current: dict | None = None
    qualification_re = re.compile(r"\b(bachelor|master|doctor|ph\.?d|b\.?tech|m\.?tech|b\.?e\.?|m\.?e\.?|b\.?sc|m\.?sc|bca|mca|diploma|intermediate|matriculat|class\s*(?:x|xi|xii|10|12)|grade\s*(?:10|12))\b", re.I)
    institution_re = re.compile(r"\b(university|institute|college|school|academy|polytechnic)\b", re.I)
    result_re = re.compile(r"\b(cgpa|gpa|percentage|marks?|score|division)\b", re.I)
    date_re = re.compile(r"\b(?:19|20)\d{2}\b|present|expected", re.I)

    def new_record():
        return {"qualification": "", "institution": "", "period": "", "result": "", "details": []}

    for raw in lines:
        line = raw.strip(" •▪●◦|:-–—")
        if not line:
            continue
        is_qualification = bool(qualification_re.search(line))
        is_institution = bool(institution_re.search(line))
        if current is None or (is_qualification and current["qualification"]):
            if current:
                records.append(current)
            current = new_record()
        elif is_institution and current["qualification"] and current["institution"]:
            records.append(current)
            current = new_record()

        current["details"].append(line)
        if is_qualification and not current["qualification"]:
            current["qualification"] = line
        elif is_institution and not current["institution"]:
            current["institution"] = line
        elif result_re.search(line) and not current["result"]:
            current["result"] = line
        elif date_re.search(line) and not current["period"]:
            current["period"] = line
    if current:
        records.append(current)
    return records


def _looks_like_project_title(line: str) -> bool:
    if len(line) > 100 or re.search(r"[.!?:]$", line) or re.search(r"\b(?:19|20)\d{2}\b.*(?:[-–—]|\bto\b).*\b(?:(?:19|20)\d{2}|present|current)\b", line, re.I):
        return False
    if re.match(r"(?i)^(project\s+github|github|tools?\b|tech(?:nology)?\s+stack\b|skill\s+stack\b|technologies\b|libraries\b|model\s+integrating\b)", line):
        return False
    if re.search(r"(?i)\b(hackathon|challenge|conference|competition|published\s+study|mdpi\s+study)\b", line):
        return False
    if re.match(r"(?i)^(developed|implemented|performed|optimized|linked|built|deployed|created|designed|addressed|used|trained|analyzed|conducted)\b", line):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z0-9&'-]*", line)
    if len(words) == 1:
        return words[0].lower() not in SKILL_VOCAB and words[0][0].isupper()
    return 2 <= len(words) <= 12 and sum(word[0].isupper() for word in words[:3]) >= 2


def _group_projects(lines: list[str]) -> list[dict]:
    projects = []

    def start(title):
        return {"title": title, "details": [], "tools": [], "links": []}

    for raw in lines:
        marked = raw.startswith("\x01")
        line = raw[1:] if marked else raw
        line = line.removeprefix("• ").strip()
        urls = re.findall(r"\[\[URL:([^\]]+)\]\]|(https?://\S+)", line)
        url_values = [a or b for a, b in urls]
        line = re.sub(r"\s*\[\[URL:[^\]]+\]\]|\s*https?://\S+", "", line).strip(" \t-–—|:")
        title_line = _looks_like_project_title(line)
        link_line = bool(re.search(r"(?i)\b(github|repository|source code|project link|live demo)\b", line)) and not title_line
        started_title = False
        likely_new_title = title_line and (marked or not projects or len(projects[-1]["details"]) >= 2)
        if likely_new_title:
            projects.append(start(line))
            started_title = True
        elif not projects:
            projects.append(start(line if title_line else "Project"))
            started_title = title_line
        if not started_title and link_line:
            label = "GitHub" if re.search(r"(?i)github", line) else "Project link"
            projects[-1]["links"].append({"label": label, "url": None})
        elif not started_title and re.match(r"(?i)^tools?(?:\s*&\s*libraries)?\s*:", line):
            value = line.split(":", 1)[1]
            projects[-1]["tools"].extend(x.strip(" •▪●◦.,") for x in re.split(r"[,;|]", value) if x.strip(" •▪●◦.,"))
        elif not started_title and re.match(r"(?i)^(?:tech(?:nology)?\s+stack|skills?)\s*:", line):
            value = line.split(":", 1)[1]
            projects[-1]["tools"].extend(x.strip(" •▪●◦.,") for x in re.split(r"[,;|]", value) if x.strip(" •▪●◦.,"))
        elif not started_title:
            if line:
                projects[-1]["details"].append(line.removeprefix("• ").strip())
        for url in url_values:
            clean_url = url.rstrip(".,)")
            label = "GitHub" if "github" in clean_url.lower() else "Project link"
            if projects[-1]["links"] and projects[-1]["links"][-1]["url"] is None:
                projects[-1]["links"][-1]["url"] = clean_url
            else:
                projects[-1]["links"].append({"label": label, "url": clean_url})
    return projects


def _experience_years(sections: dict[str, list[str]]) -> float | None:
    work_text = " ".join(sections["employment"])
    summary_text = " ".join(sections["summary"])
    mentions = re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", work_text, re.I)
    if not mentions:
        mentions = re.findall(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+)?experience\b", summary_text, re.I)
    if mentions:
        return max(float(n) for n in mentions)
    years = []
    for start, end in re.findall(r"\b(20\d{2})\s*[-–—]\s*(20\d{2}|present|current)\b", work_text, re.I):
        years.append((int(start), date.today().year if end.lower() in {"present", "current"} else int(end)))
    return float(max(0, max(end for _, end in years) - min(start for start, _ in years))) if years else None


def _header_name(text: str) -> str | None:
    for raw in text.splitlines()[:12]:
        line = re.sub(r"[\u200b\ufeff]", "", raw).strip()
        if not line:
            continue
        heading = re.sub(r"\s+", " ", line.strip(" •▪●◦|:-–—").lower())
        if heading in SECTION_NAMES:
            break
        line = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?:\+?\d[\d ().-]{7,}\d)|https?://\S+", " ", line)
        first = re.split(r"[|•▪●◦]", line, maxsplit=1)[0]
        words = re.findall(r"[A-Za-z][A-Za-z.'’\-]*", first)
        if 2 <= len(words) <= 4 and all(w.lower() not in {"resume", "curriculum", "vitae", "profile"} for w in words):
            return " ".join(words)
    return None


def extract_profile(text: str) -> dict:
    # spaCy provides sentence boundaries/entities when installed with a model; regex remains a safe fallback.
    global _nlp, _nlp_checked
    if not _nlp_checked:
        _nlp_checked = True
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except (ImportError, OSError, ValueError):
            pass
    if _nlp:
        doc = _nlp(text[:100000])
        sentences = [s.text.strip() for s in doc.sents if s.text.strip()]
        person = next((e.text for e in doc.ents if e.label_ == "PERSON"), None)
    else:
        sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
        person = None
    sections = _resume_sections(text)
    email = next(iter(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)), None)
    name = _header_name(text) or person
    skills = sorted({normalize_skill(s) for s in SKILL_VOCAB if re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w)", text, re.I)})
    education = [s[:350] for s in sections["education"]][:20]
    employment = [s[:450] for s in sections["employment"] if not re.search(r"\b(project|github|built|developed|created|implemented)\b", s, re.I)][:15]
    projects = _group_projects(sections["projects"])
    if not sections["employment"]:
        employment = [s[:450] for s in sentences if re.search(r"\b(engineer|developer|analyst|manager|intern|consultant)\b", s, re.I) and not re.search(r"\b(project|github)\b", s, re.I)][:15]
    if not projects:
        projects = [s[:450] for s in sentences if re.search(r"\b(project|github|built|developed|created|implemented)\b", s, re.I) and s[:450] not in employment][:15]
    skill_sources = [(line, "Work") for line in employment]
    for project in projects:
        if isinstance(project, dict):
            skill_sources.extend((line, "Project") for line in [project["title"], *project["details"], *project["tools"]])
            skill_sources.extend((link["url"] or link["label"], "Project") for link in project["links"])
        else:
            skill_sources.append((project, "Project"))
    evidence = {}
    for skill in skills:
        match = next(((line, label) for line, label in skill_sources if re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", line, re.I)), None)
        if match:
            snippet = re.sub(r"\s+", " ", match[0]).strip(" •▪●◦–—-|")
            evidence[skill] = f"{match[1]}: {snippet[:180].rstrip()}"
        elif any(re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", line, re.I) for line in sections["skills"]):
            evidence[skill] = "Listed in technical skills."
        else:
            snippet = next((s[:180] for s in sentences if re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", s, re.I)), "")
            evidence[skill] = snippet
    return {"name": name[:200] if name else None, "email": email, "skills": skills, "education": education,
            "experience_years": _experience_years(sections), "employment": employment, "projects": projects, "evidence": evidence}


def extract_job(description: str) -> dict:
    lines = [x.strip(" -*\t") for x in description.splitlines() if x.strip()]
    title = next((line for line in lines[:5] if len(line) < 120 and re.search(r"\b(engineer|developer|analyst|manager|designer|scientist|specialist|architect|intern|consultant|administrator)\b", line, re.I)), "New role")
    required = set()
    preferred = set()
    quals = []
    target = required
    for line in lines:
        if re.search(r"preferred|nice to have|bonus", line, re.I): target = preferred
        elif re.search(r"required|must have|requirements", line, re.I): target = required
        for skill in SKILL_VOCAB:
            if re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", line, re.I): target.add(normalize_skill(skill))
        if re.search(r"\b(bachelor|master|ph\.?d|degree|diploma|certification|b\.?tech|b\.?e\.?|b\.?sc|bca|cgpa|gpa)\b", line, re.I): quals.append(line[:250])
    # Skill mentions without a section label are treated as required.
    mentions = {normalize_skill(s) for s in SKILL_VOCAB if re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w)", description, re.I)}
    required |= mentions - preferred
    exp = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", description, re.I)
    return {"title": title, "required_skills": sorted(required), "preferred_skills": sorted(preferred - required),
            "min_experience": float(exp.group(1)) if exp else None, "qualifications": quals}
