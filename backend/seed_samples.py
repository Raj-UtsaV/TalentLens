"""Generate ten fictional DOCX resumes for local demos; contains no real people."""
from pathlib import Path

from docx import Document

OUT = Path(__file__).parent / "sample_data"
PEOPLE = [
    ("Avery Morgan", "Python FastAPI PostgreSQL Docker AWS", 7, "Master of Science in Computer Science", "Built scalable REST API services and automated deployments."),
    ("Jordan Lee", "Python Django SQL AWS Git", 5, "Bachelor of Science in Software Engineering", "Developed data processing tools and owned production services."),
    ("Casey Patel", "Python FastAPI SQL Docker Kubernetes", 4, "Bachelor of Computer Science", "Led a migration to containerized services and built REST APIs."),
    ("Riley Chen", "Java Spring SQL AWS Docker", 8, "Master of Computer Science", "Designed cloud applications and coached engineering teams."),
    ("Taylor Kim", "Python Flask PostgreSQL Git Linux", 3, "Bachelor of Science in Information Technology", "Created internal APIs and data analysis projects."),
    ("Morgan Diaz", "Python FastAPI PostgreSQL AWS Kubernetes", 6, "Master of Science in Computer Science", "Implemented reliable backend platforms and deployment pipelines."),
    ("Quinn Brooks", "JavaScript Node.js React MongoDB Docker", 5, "Bachelor of Science in Computer Science", "Built full stack products and REST API integrations."),
    ("Jamie Rivera", "Python SQL pandas machine learning scikit-learn", 4, "Master of Data Science", "Developed machine learning models and data pipelines."),
    ("Alex Kimani", "Python Django PostgreSQL Docker Git", 2, "Bachelor of Software Engineering", "Built web services, wrote tests, and supported production releases."),
    ("Samira Noor", "Python FastAPI SQL AWS Git", 9, "Master of Science in Software Engineering", "Architected backend systems and mentored developers."),
]

OUT.mkdir(exist_ok=True)
for i, (name, skills, years, education, project) in enumerate(PEOPLE, 1):
    doc = Document(); doc.add_heading(name, 0); doc.add_paragraph(f"{name.lower().replace(' ', '.')}@example.test")
    doc.add_heading("Professional Summary", level=1); doc.add_paragraph(f"Software professional with {years} years of experience. Experienced in {skills}.")
    doc.add_heading("Skills", level=1); doc.add_paragraph(skills)
    doc.add_heading("Experience", level=1); doc.add_paragraph(f"Software Engineer at Example {2025-years}–2025. {project}")
    doc.add_heading("Projects", level=1); doc.add_paragraph(project)
    doc.add_heading("Education", level=1); doc.add_paragraph(education)
    doc.save(OUT / f"candidate_{i:02}.docx")
print(f"Generated {len(PEOPLE)} synthetic DOCX resumes in {OUT}")
