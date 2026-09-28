from database import db_session_basede26
from models import UserDB
from auth_utils import hash_password


def create_test_user():
    db = db_session_basede26()

    try:
        existing_user = (
            db.query(UserDB)
            .filter(UserDB.email == "admin@example.com")
            .first()
        )

        if existing_user:
            print("Test user already exists.")
            return

        user = UserDB(
            name="Admin User",
            email="admin@example.com",
            password_hash=hash_password("password123")
        )

        db.add(user)
        db.commit()

        print("Test user created successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    create_test_user()