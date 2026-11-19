import hashlib
import re
from urllib.parse import quote
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import Candidate, Job
from .schemas import JobCreate, JobPreview, JobUpdate, Weights
from .services.extraction import extract_job, extract_profile, group_education, matching_text
from .services.parsing import DocumentError, extract_text
from .services.scoring import score_candidate


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if "document_data" not in {column["name"] for column in inspect(engine).get_columns("candidates")}:
        binary_type = "BYTEA" if engine.dialect.name == "postgresql" else "BLOB"
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE candidates ADD COLUMN document_data {binary_type}"))
    yield


app = FastAPI(title="Resume Match", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()


@app.get("/api/health")
def health(): return {"status": "ok"}


@app.post("/api/jobs", status_code=201)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    return save_job(payload.description, db, payload)


def save_job(description: str, db: Session, payload: JobCreate | None = None):
    extracted = extract_job(description)
    payload = payload or JobCreate(description=description)
    job = Job(title=payload.title or extracted["title"], description=description,
              required_skills=payload.required_skills if payload.required_skills is not None else extracted["required_skills"],
              preferred_skills=payload.preferred_skills if payload.preferred_skills is not None else extracted["preferred_skills"],
              min_experience=payload.min_experience if payload.min_experience is not None else extracted["min_experience"],
              qualifications=payload.qualifications if payload.qualifications is not None else extracted["qualifications"])
    db.add(job); db.commit(); db.refresh(job)
    return job_out(job, db)


@app.post("/api/jobs/file", status_code=201)
async def create_job_from_file(file: UploadFile = File(...), title: str | None = Form(default=None), db: Session = Depends(get_db)):
    content = await file.read(15 * 1024 * 1024 + 1)
    if len(content) > 15 * 1024 * 1024: raise HTTPException(413, "File exceeds 15 MB limit")
    try: description = extract_text(file.filename or "job.pdf", content)
    except DocumentError as exc: raise HTTPException(422, str(exc)) from exc
    if len(description) < 20: raise HTTPException(422, "Job description must contain at least 20 readable characters")
    return save_job(description, db, JobCreate(description=description, title=title))


@app.patch("/api/jobs/{job_id}", status_code=200)
def update_job(job_id: int, payload: JobUpdate, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if payload.description is not None:
        extracted = extract_job(payload.description)
        job.description = payload.description
        job.required_skills = extracted["required_skills"]
        job.preferred_skills = extracted["preferred_skills"]
        job.min_experience = extracted["min_experience"]
        job.qualifications = extracted["qualifications"]
        job.title = payload.title or extracted["title"]
    if payload.title is not None:
        job.title = payload.title
    reanalyze_candidates(job, db)
    db.refresh(job)
    return job_out(job, db)


def reanalyze_candidates(job: Job, db: Session):
    criteria = {"required_skills": job.required_skills, "preferred_skills": job.preferred_skills,
                "min_experience": job.min_experience, "qualifications": job.qualifications,
                "description": job.description}
    for candidate in job.candidates:
        profile = extract_profile(candidate.parsed_text)
        score = score_candidate(criteria, {**profile, "parsed_text": matching_text(candidate.parsed_text, profile["name"])},
                                candidate.scores.get("weights"))
        for key, value in {**profile, **score}.items():
            setattr(candidate, key, value)
    db.commit()
    return db.scalars(select(Candidate).where(Candidate.job_id == job.id).order_by(Candidate.overall_score.desc())).all()


@app.post("/api/jobs/{job_id}/reanalyze", status_code=200)
def reanalyze_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return [candidate_out(candidate) for candidate in reanalyze_candidates(job, db)]


@app.post("/api/jobs/{job_id}/preview", status_code=200)
def preview_job_update(job_id: int, payload: JobPreview, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    extracted = extract_job(payload.description)
    criteria = {**extracted, "description": payload.description}
    previews = []
    for candidate in job.candidates:
        profile = extract_profile(candidate.parsed_text)
        score = score_candidate(criteria, {**profile, "parsed_text": matching_text(candidate.parsed_text, profile["name"])}, candidate.scores.get("weights"))
        previews.append({"id": candidate.id, "name": profile["name"] or candidate.filename,
                         "previous_score": candidate.overall_score, "new_score": score["overall_score"],
                         "delta": round(score["overall_score"] - candidate.overall_score, 2),
                         "matched_skills": score["matched_skills"], "missing_skills": score["missing_skills"]})
    previews.sort(key=lambda item: item["new_score"], reverse=True)
    return {"candidate_count": len(previews), "candidates": previews}


def job_out(job, db: Session):
    candidate_count = db.scalar(select(func.count(Candidate.id)).where(Candidate.job_id == job.id)) or 0
    return {"id": job.id, "title": job.title, "description": job.description, "required_skills": job.required_skills,
            "preferred_skills": job.preferred_skills, "min_experience": job.min_experience, "qualifications": job.qualifications,
            "candidate_count": candidate_count}


@app.get("/api/jobs")
def list_jobs(db: Session = Depends(get_db)):
    return [job_out(j, db) for j in db.scalars(select(Job).order_by(Job.created_at.desc())).all()]


@app.post("/api/jobs/{job_id}/resumes")
async def upload_resumes(job_id: int, files: list[UploadFile] = File(...), weights: Weights = Depends(), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job: raise HTTPException(404, "Job not found")
    if len(files) > 100: raise HTTPException(413, "Upload up to 100 resumes at a time")
    results = []
    for file in files:
        filename = (file.filename or "resume").replace("/", "_").replace("\\", "_")[:255]
        try:
            content = await file.read(15 * 1024 * 1024 + 1)
            if len(content) > 15 * 1024 * 1024: raise DocumentError("File exceeds 15 MB limit")
            digest = hashlib.sha256(content).hexdigest()
            existing = db.scalar(select(Candidate).where(Candidate.job_id == job_id, Candidate.file_hash == digest))
            text = extract_text(filename, content)
            profile = extract_profile(text)
            score = score_candidate({"required_skills": job.required_skills, "preferred_skills": job.preferred_skills,
                                     "min_experience": job.min_experience, "qualifications": job.qualifications, "description": job.description},
                                    {**profile, "parsed_text": matching_text(text, profile["name"])}, weights.model_dump())
            if existing:
                for key, value in {**profile, **score, "filename": filename, "parsed_text": text, "document_data": content}.items():
                    setattr(existing, key, value)
                db.commit()
                results.append({"filename": filename, "status": "duplicate", "candidate_id": existing.id,
                                "message": "Existing candidate refreshed with current parsing and scoring."})
                continue
            candidate = Candidate(job_id=job_id, filename=filename, file_hash=digest, parsed_text=text,
                                  document_data=content, **profile, **score)
            db.add(candidate); db.commit(); db.refresh(candidate)
            results.append({"filename": filename, "status": "processed", "candidate_id": candidate.id})
        except DocumentError as exc:
            results.append({"filename": filename, "status": "error", "error": str(exc)})
        except Exception:
            db.rollback()
            results.append({"filename": filename, "status": "error", "error": "Could not process this resume"})
    return {"results": results}


def candidate_out(c):
    return {"id": c.id, "filename": c.filename, "name": c.name, "experience_years": c.experience_years,
            "overall_score": c.overall_score, "scores": c.scores, "matched_skills": c.matched_skills, "missing_skills": c.missing_skills}


@app.get("/api/jobs/{job_id}/candidates")
def list_candidates(job_id: int, db: Session = Depends(get_db)):
    if not db.get(Job, job_id): raise HTTPException(404, "Job not found")
    candidates = db.scalars(select(Candidate).where(Candidate.job_id == job_id).order_by(Candidate.overall_score.desc())).all()
    return [candidate_out(c) for c in candidates]


@app.get("/api/candidates/{candidate_id}")
def candidate_detail(candidate_id: int, db: Session = Depends(get_db)):
    c = db.get(Candidate, candidate_id)
    if not c: raise HTTPException(404, "Candidate not found")
    # Email is deliberately excluded from matching and omitted from analysis output.
    profile = extract_profile(c.parsed_text)
    education = profile["education"] or c.education
    return {**candidate_out(c), "name": profile["name"] or c.name, "experience_years": profile["experience_years"],
            "skills": profile["skills"] or c.skills, "education": education,
            "education_records": group_education(education), "employment": profile["employment"] or c.employment,
            "projects": profile["projects"] or c.projects,
            "criteria": {"required_skills": c.job.required_skills or [], "preferred_skills": c.job.preferred_skills or [],
                         "min_experience": c.job.min_experience, "qualifications": c.job.qualifications or []},
            "has_original_file": bool(c.document_data), "evidence": profile["evidence"] or c.evidence, "explanation": c.explanation}


@app.get("/api/candidates/{candidate_id}/resume", status_code=200)
def candidate_resume(candidate_id: int, db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    if not candidate.document_data:
        raise HTTPException(404, "The original file is unavailable. Re-upload this resume to enable the PDF viewer.")
    is_pdf = candidate.filename.lower().endswith(".pdf")
    media_type = "application/pdf" if is_pdf else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    disposition = "inline" if is_pdf else "attachment"
    filename = quote(candidate.filename.replace('"', ""))
    return Response(content=candidate.document_data, media_type=media_type,
                    headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{filename}", "Cache-Control": "no-store"})
