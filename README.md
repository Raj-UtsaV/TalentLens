# TalentLens

TalentLens is a local resume matching and ranking app. Add a job description, upload PDF or DOCX resumes, and review an explainable, ranked shortlist with candidate evidence.

The repository includes ten fictional resumes for trying the app. Candidate ranking uses job-related information; sensitive personal attributes are excluded from scoring.

For an explanation of the processing flow, score formula, design choices, and known limitations, see the [Project Guide](docs/PROJECT_GUIDE.md).

## Features

- Create a role from pasted text or an uploaded PDF/DOCX job description.
- Batch upload up to 100 resumes (15 MB each); duplicate files refresh the existing candidate.
- Extract candidate skills, education, employment history, projects, tools, links, and supporting evidence.
- Rank candidates using normalized skill matching, semantic similarity, experience, and education.
- Review score breakdowns, project cards, grouped education, and the original uploaded resume.
- Save roles and candidate results in SQLite or PostgreSQL.
- Edit saved roles with a score impact preview; new and refreshed candidates are ranked automatically.

## Requirements

- Python 3.10 or newer
- Node.js 20.19+ (or 22.12+)
- PostgreSQL is optional. SQLite is used by default.

The first semantic match downloads the `all-MiniLM-L6-v2` model from Hugging Face. Internet access is needed for that download. If it is unavailable, TalentLens falls back to a local token-overlap similarity score. Installing spaCy's English model is optional; extraction uses a regex fallback without it.

## Run locally

Run these commands from the repository root. Open two terminals: one for the API and one for the web app.

### 1. Start the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Optional: install spaCy's English model for sentence and entity extraction.

```bash
python -m spacy download en_core_web_sm
```

By default, the backend creates `backend/resume_matcher.db` and needs no database setup. To use PostgreSQL instead, create a database owned by the PostgreSQL role in your connection URL. For example, using the `utsav` role from `backend/.env.example`:

```bash
sudo systemctl start postgresql
sudo -u postgres createuser --login utsav
sudo -u postgres psql -c "ALTER ROLE utsav WITH LOGIN PASSWORD 'choose-a-password'"
sudo -u postgres createdb --owner=utsav resume_match
cp .env.example .env
```

If the `utsav` role or `resume_match` database already exists, skip its creation command. Edit `backend/.env` and replace `YOUR_PASSWORD` in `DATABASE_URL` with the role's password. If the password contains URL-reserved characters, percent-encode them in the connection URL. The `.env` file is ignored by Git; never commit your database password.

Start the API from the `backend` directory:

```bash
uvicorn app.main:app --reload
```

The API is available at <http://localhost:8000>; interactive documentation is at <http://localhost:8000/docs>.

### 2. Start the frontend

In a second terminal, from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. Vite forwards `/api` requests to the backend at `http://127.0.0.1:8000`.

### Try the fictional resumes

Ten synthetic DOCX resumes are included in `backend/sample_data/`. Select them in the UI to test batch upload. To regenerate them:

```bash
cd backend
source .venv/bin/activate
python seed_samples.py
```

The generator only creates files; upload those resumes through the UI to add them to a role.

## Configuration

The backend reads `DATABASE_URL` from `backend/.env`. If it is unset, SQLite is used. The sample PostgreSQL connection string is in [`backend/.env.example`](backend/.env.example).

PostgreSQL tables are created at startup. On startup, TalentLens also adds the original-document column to an existing candidates table if needed. Resume files uploaded after this change are stored in the configured database. Previously uploaded candidates do not contain their original file; re-upload the same resume to enable its PDF preview or DOCX download.

## API overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/jobs` | Create a role from JSON job description text |
| `POST` | `/api/jobs/file` | Create a role from an uploaded PDF/DOCX description |
| `GET` | `/api/jobs` | List saved roles and candidate counts |
| `PATCH` | `/api/jobs/{job_id}` | Edit a saved role and recalculate candidate scores |
| `POST` | `/api/jobs/{job_id}/preview` | Preview score changes before saving a role edit |
| `POST` | `/api/jobs/{job_id}/reanalyze` | Re-extract and re-score candidates for a saved role |
| `POST` | `/api/jobs/{job_id}/resumes` | Batch upload PDF/DOCX resumes |
| `GET` | `/api/jobs/{job_id}/candidates` | List candidates ordered by match score |
| `GET` | `/api/candidates/{candidate_id}` | Get candidate analysis, scores, evidence, projects, and education |
| `GET` | `/api/candidates/{candidate_id}/resume` | Preview original PDF or download original DOCX |

Resume upload accepts up to 100 files per request and 15 MB per file. Invalid or unreadable documents return a per-file error so they do not stop the rest of the batch. Scanned PDFs need OCR before upload; OCR is not included.

## Scoring

Default weights are skills 50%, semantic similarity 25%, experience 15%, and education 10%.

- **Skills:** normalized required-skill coverage; preferred skills count at half weight. Common aliases such as `K8S` and `Kubernetes` are normalized.
- **Semantic:** cosine similarity of normalized job and resume text embeddings using `all-MiniLM-L6-v2`.
- **Experience:** proportion of the job's stated minimum years, capped at 100%. It is N/A if the job has no minimum or the resume has no usable experience data.
- **Education:** degree level (50%), field match (30%), and GPA (20%) when available. Related technology fields such as CSE, IT, software engineering, AI/data science, and electronics receive full field-match credit. Degree priority is M.Tech/master's > B.Tech/bachelor's > Class 12 > Class 10; candidates meeting or exceeding an explicitly requested level receive full degree credit.

If a component is missing or not applicable, its weight is excluded and the remaining weights are renormalized. Each component and the final score stay between 0 and 100. Scores support recruiter review; they are not an automated hiring decision.

## Tests and production build

Run backend tests:

```bash
cd backend
source .venv/bin/activate
python -m pytest -q
```

Build the frontend bundle:

```bash
cd frontend
npm ci
npm run build
```

The frontend build is written to `frontend/dist/` (ignored by Git). The development server is for local use; production deployments should serve the built assets behind a web server or hosting platform and configure it to proxy `/api` to FastAPI.
