import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#auth / JWT
# This signs every login token. 
SECRET_KEY = os.environ.get(
    "SECRET_KEY", "Enteryourownkey1"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120  # 2 hours, then they have to log back in

# file storage
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB — production photos can get big

#celery/redis
# Redis is the task queue (broker) here 
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", f"{REDIS_URL}/0")

# vision model state 
# The model keeps a small running record of "what normal images look like"
MODEL_STATE_DIR = os.path.join(PROJECT_ROOT, "model_state")
os.makedirs(MODEL_STATE_DIR, exist_ok=True)
