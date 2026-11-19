from io import BytesIO

from docx import Document

from app.services.extraction import extract_profile, group_education, matching_text, normalize_skill
from app.services.parsing import DocumentError, extract_text
from app.services.scoring import score_candidate


def test_docx_parsing_and_profile():
    doc = Document(); doc.add_paragraph("Avery Morgan"); doc.add_paragraph("avery@example.test")
    doc.add_paragraph("Software engineer with 5 years of professional experience.")
    doc.add_paragraph("Skills: Python, FastAPI and PostgreSQL.")
    doc.add_paragraph("Education: Bachelor of Science in Computer Science.")
    stream = BytesIO(); doc.save(stream)
    text = extract_text("resume.docx", stream.getvalue())
    profile = extract_profile(text)
    assert "Python" in text and profile["email"] == "avery@example.test"
    assert profile["experience_years"] == 5


def test_rejects_empty_or_scanned_document():
    doc = Document(); doc.add_paragraph(" ")
    stream = BytesIO(); doc.save(stream)
    try: extract_text("scan.docx", stream.getvalue())
    except DocumentError as exc: assert "No readable text" in str(exc)
    else: raise AssertionError("empty document accepted")


def test_skill_aliases_and_score_bounds():
    assert normalize_skill("K8S") == "kubernetes"
    job = {"required_skills": ["Python", "Postgres"], "preferred_skills": [], "description": "python backend role", "min_experience": 4, "qualifications": []}
    person = {"skills": ["python"], "experience_years": 2, "education": [], "parsed_text": "python backend engineer"}
    result = score_candidate(job, person, semantic_fn=lambda *_: .5)
    assert result["matched_skills"] == ["python"]
    assert result["missing_skills"] == ["postgresql"]
    assert 0 <= result["overall_score"] <= 100
    assert result["scores"]["skills"] == 50


def test_semantic_text_removes_identifying_and_sensitive_details():
    clean = matching_text("Avery Morgan\navery@example.test\nPhone: 555-123-4567\nAge: 42\nPython backend engineer", "Avery Morgan")
    assert "Avery" not in clean and "example.test" not in clean and "555" not in clean and "42" not in clean
    assert "Python backend engineer" in clean


def test_missing_components_are_not_penalized():
    result = score_candidate({"description": "", "required_skills": [], "preferred_skills": [], "qualifications": []},
                             {"parsed_text": "", "skills": [], "education": [], "experience_years": None})
    assert result["overall_score"] == 0


def test_project_bullets_and_github_link_stay_with_their_project():
    text = """Avery Morgan
Experience
Software Engineer at Example Corp
2022–2024
Projects
• Bus Demand Forecast
Project GitHub Link
https://github.com/example/bus
– Developed a forecast using 1 year of booking data.
– Tools & Libraries: Python, Pandas, LightGBM.
• CareTwin
– Built a glucose prediction model.
Achievements
Won a data hackathon.
"""
    profile = extract_profile(text)
    assert profile["name"] == "Avery Morgan"
    assert profile["experience_years"] == 2
    assert len(profile["projects"]) == 2
    bus = profile["projects"][0]
    assert bus["title"] == "Bus Demand Forecast"
    assert bus["details"] == ["Developed a forecast using 1 year of booking data."]
    assert bus["tools"] == ["Python", "Pandas", "LightGBM"]
    assert bus["links"] == [{"label": "GitHub", "url": "https://github.com/example/bus"}]


def test_unavailable_score_components_are_not_scored():
    result = score_candidate(
        {"description": "Backend developer with 3 years experience; Bachelor degree required", "required_skills": ["Python"], "preferred_skills": [], "min_experience": 3, "qualifications": ["Bachelor degree"]},
        {"parsed_text": "Python backend developer", "skills": ["Python"], "education": [], "experience_years": None},
        semantic_fn=lambda *_: .5,
    )
    assert result["scores"]["experience"] is None
    assert result["scores"]["education"] is None
    assert result["overall_score"] == 83.33
    assert "experience" in result["explanation"].lower()


def test_education_score_separates_degree_field_and_gpa():
    result = score_candidate(
        {"description": "", "required_skills": [], "preferred_skills": [], "qualifications": ["B.Tech in CSE, minimum 8 CGPA"]},
        {"parsed_text": "", "skills": [], "experience_years": None,
         "education": ["Bachelor of Technology in Civil Engineering", "CGPA: 9/10"]},
        semantic_fn=lambda *_: 0,
    )
    assert result["scores"]["education"] == 70


def test_related_technology_branch_gets_full_education_credit():
    result = score_candidate(
        {"description": "", "required_skills": [], "preferred_skills": [], "qualifications": ["B.Tech in CSE, minimum 8 CGPA"]},
        {"parsed_text": "", "skills": [], "experience_years": None,
         "education": ["Bachelor of Technology in Information Technology", "CGPA: 9/10"]},
        semantic_fn=lambda *_: 0,
    )
    assert result["scores"]["education"] == 100


def test_education_priority_mtech_then_btech_then_class_twelve_then_ten():
    job = {"description": "", "required_skills": [], "preferred_skills": [], "qualifications": ["M.Tech in CSE"]}
    education_by_level = [
        ["M.Tech in CSE"], ["B.Tech in CSE"], ["Intermediate in CSE"], ["Class X in CSE"],
    ]
    scores = [score_candidate(job, {"parsed_text": "", "skills": [], "experience_years": None, "education": education}, semantic_fn=lambda *_: 0)["scores"]["education"] for education in education_by_level]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 100


def test_education_details_are_grouped_per_qualification():
    records = group_education([
        "National Institute of Technology Agartala", "CGPA: 8.45/10",
        "Bachelor of Technology in Computational Mathematics", "2023 – 2027 (Expected)",
        "Ram Lakhan Singh Avadh College, Premraj, Mahua", "Percentage: 71.3%", "Intermediate (XII)",
        "2021 – 2023", "Holy Mission Senior Secondary School", "Percentage: 87.2%", "Matriculate (X)",
        "2020 – 2021",
    ])
    assert len(records) == 3
    assert records[0]["qualification"] == "Bachelor of Technology in Computational Mathematics"
    assert records[0]["institution"] == "National Institute of Technology Agartala"
    assert records[0]["result"] == "CGPA: 8.45/10"
    assert records[0]["period"] == "2023 – 2027 (Expected)"
    assert records[1]["qualification"] == "Intermediate (XII)"
    assert records[1]["institution"].startswith("Ram Lakhan")


def test_project_bullets_dates_stack_and_urls_stay_with_their_project():
    text = """Avery Morgan
Projects
• Bus Demand Forecast
April 2025 – May 2025
Project GitHub Link [[URL:https://github.com/example/bus]]
– Developed a forecast using historical booking data.
• Tech Stack: Python, Pandas, LightGBM
• CareTwin
– Built a glucose prediction model.
"""
    projects = extract_profile(text)["projects"]
    assert len(projects) == 2
    assert projects[0]["title"] == "Bus Demand Forecast"
    assert projects[0]["details"] == ["April 2025 – May 2025", "Developed a forecast using historical booking data."]
    assert projects[0]["tools"] == ["Python", "Pandas", "LightGBM"]
    assert projects[0]["links"] == [{"label": "GitHub", "url": "https://github.com/example/bus"}]
    assert projects[1]["title"] == "CareTwin"
