# DefectSense AI

A defect detection platform for production lines. An operator uploads a photo of a part, a vision model checks it for anything that looks off, and a human inspector makes the final call before anything gets logged for good.

I built this as a portfolio project to put together a backend that actually does the things a real one would need to do — proper auth and roles, a real (if lightweight) ML model, a task queue instead of just running everything inline, and an audit trail you could actually hand to someone.

## What it does

The core flow is simple: upload → AI check → human review → permanent record.

- **Image upload and analysis** — operators upload photos, which get queued and run through a vision model in the background. The upload responds immediately, it doesn't sit there waiting for the model to finish.
- **AI-assisted detection** — the model isn't a hardcoded classifier. It uses a pretrained CNN (MobileNetV3-Small) as a feature extractor and flags images that look unusually different from what it's seen so far. There's no labeled "good vs bad" dataset to train a real classifier on yet, so this anomaly-detection approach is a reasonable stand-in until there is one.
- **Human review queue** — every flagged image goes to an inspector, who can confirm it or override the AI. When they clear something, that image gets folded back into the model's idea of "normal," so the baseline improves over time.
- **Role-based access** — three roles (operator, inspector, manager), each with a different view and a different set of things they're allowed to do. Enforced on the backend, not just hidden in the UI.
- **Account management** — users can update their own profile and password. Managers get a dashboard to see every account, change roles, disable/enable users, and reset someone's password if they're locked out.
- **Full audit trail** — every upload, every AI verdict, and every human decision is its own row in the database with a timestamp. You can reconstruct the full history of any image.
- **Stats dashboard** — defect rate, how often the AI and the human agreed, and where everything currently sits in the pipeline, for managers.

## Tech Stack

**Backend**
- FastAPI — the web framework, handles all the API routes
- Uvicorn — runs the FastAPI app
- SQLAlchemy — ORM, talks to the database
- SQLite — the database itself (easy to swap for Postgres later, nothing else has to change)
- python-jose — signs and verifies the JWT login tokens
- passlib + bcrypt — hashes passwords, never stores them in plain text

**Task Queue**
- Celery — runs the AI analysis as a background job instead of blocking the upload request
- Redis — the message broker Celery uses to pass jobs to a worker

**Vision Model**
- PyTorch + torchvision — loads MobileNetV3-Small (pretrained on ImageNet) and runs it
- NumPy — handles the distance math behind the anomaly scoring
- Pillow — opens and validates uploaded images

**Frontend**
- Plain HTML, CSS, and JavaScript — no framework, no build step, just one file

## Getting It Running

You'll need Python 3.10+ and Redis. Here's the full setup from a clean clone.

### 1. Clone the repo and install dependencies

```bash
git clone <your-repo-url>
cd defect-detection
pip install -r requirements.txt
```

This also pulls in PyTorch, so the first install takes a few minutes.

### 2. Install Redis (if you don't already have it)

**macOS:**
```bash
brew install redis
```

**Ubuntu/Debian:**
```bash
sudo apt-get install redis-server
```

**Windows:** easiest is Docker — `docker run -d -p 6379:6379 redis`

### 3. Start everything — you'll need three terminals open at once

**Terminal 1 — Redis:**
```bash
redis-server
```

**Terminal 2 — the Celery worker** (this is what actually runs the AI model on each upload):
```bash
celery -A app.celery_app worker --loglevel=info --concurrency=1
```

**Terminal 3 — the app itself:**
```bash
python run.py
```

### 4. Open it

Go to **http://localhost:8000** in your browser.

The first time the worker starts, it downloads MobileNetV3-Small's pretrained weights (about 10MB, from a normal public CDN, no account needed). If that download ever fails — no internet, a locked-down network, whatever — the app falls back to a simpler heuristic automatically instead of breaking.

### 5. Log in

Three accounts get created automatically the first time you run it:

| Role | Username | Password |
|------|----------|----------|
| Manager | `admin` | `admin123` |
| Inspector | `inspector1` | `inspect123` |
| Operator | `operator1` | `operate123` |

Log in as `operator1`, upload a photo, then switch to `inspector1` to see it sitting in the review queue.

---
