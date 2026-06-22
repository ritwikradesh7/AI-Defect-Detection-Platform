# Starts the web server. 

import sys
import uvicorn
from app.database import engine, SessionLocal, Base
from app import models
from app.auth import hash_password
from app.config import REDIS_URL


def create_tables():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("   done (or they already existed).")


def create_default_users():
    
    db = SessionLocal()

    starter_users = [
        {"username": "admin",      "email": "admin@defectsense.com",      "password": "admin123",   "role": "manager"},
        {"username": "inspector1", "email": "inspector@defectsense.com",  "password": "inspect123", "role": "inspector"},
        {"username": "operator1",  "email": "operator@defectsense.com",   "password": "operate123", "role": "operator"},
    ]

    created_any = False
    skipped = []

    for user_data in starter_users:
        username_taken = db.query(models.User).filter(
            models.User.username == user_data["username"]
        ).first()
        if username_taken:
            continue 

        email_taken = db.query(models.User).filter(
            models.User.email == user_data["email"]
        ).first()
        if email_taken:
            
            skipped.append((user_data["username"], user_data["email"], email_taken.username))
            continue

        db.add(models.User(
            username        = user_data["username"],
            email           = user_data["email"],
            hashed_password = hash_password(user_data["password"]),
            role            = user_data["role"],
        ))
        db.commit()  
        created_any = True

    db.close()

    if created_any:
        print("\nDefault accounts created:")
        print("   manager:    admin       / admin123")
        print("   inspector:  inspector1  / inspect123")
        print("   operator:   operator1   / operate123")
    else:
        print("   default users already exist, skipping.")

    if skipped:
        print("\n   Note: skipped re-creating these demo accounts — their email")
        print("   is already attached to a different account (probably renamed):")
        for username, email, current_owner in skipped:
            print(f"     - '{username}' ({email}) is now owned by '{current_owner}'")


def check_redis():
    try:
        import redis
        client = redis.from_url(REDIS_URL, socket_connect_timeout=2)
        client.ping()
        print(f"   Redis reachable at {REDIS_URL}")
    except Exception as e:
        print(f"   WARNING: couldn't reach Redis at {REDIS_URL} ({e})")
        print("   Uploads will queue but nothing will process them until")
        print("   Redis is running and a Celery worker is started.")


def main():
    print("=" * 60)
    print("  DefectSense AI — Defect Detection Platform")
    print("=" * 60)

    create_tables()

    print("\nSetting up default users...")
    create_default_users()

    print("\nChecking Redis...")
    check_redis()

    print("\n" + "=" * 60)
    print("Starting server...")
    print("   App:  http://localhost:8000")
    print("   Docs: http://localhost:8000/docs")
    print("   (remember: the Celery worker is a separate process — see top of this file)")
    print("=" * 60 + "\n")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


if __name__ == "__main__":
    main()
