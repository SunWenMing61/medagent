"""Create an administrator without shipping default credentials."""

import argparse
import getpass

from app.core.security import hash_password
from app.db.session import MySQLSessionLocal
from app.models.user import User


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--email")
    args = parser.parse_args()
    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation or len(password) < 12:
        raise SystemExit("Passwords must match and contain at least 12 characters")
    db = MySQLSessionLocal()
    try:
        if db.query(User.id).filter(User.username == args.username).first():
            raise SystemExit("Username already exists")
        db.add(
            User(
                username=args.username,
                email=args.email,
                password_hash=hash_password(password),
                role="admin",
                status=1,
            )
        )
        db.commit()
    finally:
        db.close()
    print("Administrator created")


if __name__ == "__main__":
    main()
