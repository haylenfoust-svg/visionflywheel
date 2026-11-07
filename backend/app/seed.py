"""Seed the first admin account — run `python -m app.seed` from `backend/`.

Usage:
    python -m app.seed                      # admin / admin123 (dev only)
    python -m app.seed --username root --password 'S3cure!'
"""

from __future__ import annotations

import argparse

from app.core.database import SessionLocal, init_db
from app.core.security import hash_password
from app.models.user import User


def seed_admin(username: str, password: str, display_name: str | None = None) -> User:
    init_db()
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            print(f"[seed] user already exists: {username} (role={existing.role})")  # noqa: T201
            return existing
        user = User(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            display_name=display_name or "Administrator",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"[seed] created admin: {username} (id={user.id})")  # noqa: T201
        return user
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the first VisionFlywheel admin account.")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--display-name", default="Administrator")
    args = parser.parse_args()

    if args.password == "admin123":
        print("[seed] WARNING: using the default dev password. Change it in production.")  # noqa: T201

    seed_admin(args.username, args.password, args.display_name)


if __name__ == "__main__":
    main()
