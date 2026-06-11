"""Yönetici (admin) kullanıcısı oluşturur veya mevcut kullanıcıyı admin yapar.

Kullanım:
    python scripts/create_admin.py --username admin --password "GucluParola"
    # veya ortam değişkenleriyle:
    ADMIN_USERNAME=admin ADMIN_PASSWORD=... python scripts/create_admin.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import User, UserRole  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Admin kullanıcı oluştur/yükselt")
    parser.add_argument("--username", default=os.getenv("ADMIN_USERNAME"))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD"))
    parser.add_argument("--first-name", default="Yönetici")
    args = parser.parse_args()

    if not args.username or not args.password:
        raise SystemExit("--username ve --password (veya ADMIN_USERNAME/ADMIN_PASSWORD) gerekli.")

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == args.username))
        if user is None:
            user = User(username=args.username, first_name=args.first_name)
            db.add(user)
        user.password_hash = hash_password(args.password)
        user.role = UserRole.admin
        user.active = True
        db.commit()
        print(f"✓ '{args.username}' admin olarak ayarlandı (id={user.id}).")


if __name__ == "__main__":
    main()
