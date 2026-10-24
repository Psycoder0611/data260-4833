"""Create the s4833_hw7 database, the users table and three demo users.

Run:  python init_hw7_db.py
Safe to run again: users that already exist are kept as they are.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from hw7 import config
from hw7.db import Base, HW7User, SessionLocal, engine
from hw7.security import hash_password


def server_url(url: URL) -> URL:
    """Return url without a database name, so we can connect to the server only.

    URL.set(database=None) keeps the old name, so the URL is rebuilt instead.
    """
    return URL.create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        query=url.query,
    )


def ensure_database() -> str:
    """Create the MySQL database if it is missing and return its name."""
    url = make_url(config.HW7_DATABASE_URL)
    server_engine = create_engine(server_url(url))
    with server_engine.connect() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{url.database}` CHARACTER SET utf8mb4"
            )
        )
        connection.commit()
    server_engine.dispose()
    return str(url.database)


def seed_users() -> list[tuple[str, str, bool]]:
    """Insert the demo users (hashed passwords). Return (name, role, created)."""
    results = []
    with SessionLocal() as session:
        for username, password, role in config.DEMO_USERS:
            existing = session.query(HW7User).filter_by(username=username).first()
            if existing is None:
                session.add(
                    HW7User(
                        username=username,
                        password_hash=hash_password(password),
                        role=role,
                    )
                )
            results.append((username, role, existing is None))
        session.commit()
    return results


def main() -> None:
    """Set up the database and show what the users table now holds."""
    name = ensure_database()
    Base.metadata.create_all(engine)
    print(f"database {name}: users table ready")
    for username, role, created in seed_users():
        print(f"  {'created' if created else 'exists '} {username} ({role})")
    print("\nusers table (password_hash shows only the first 20 characters):")
    with SessionLocal() as session:
        for user in session.query(HW7User).order_by(HW7User.id):
            print(
                f"  id={user.id} username={user.username:<15} "
                f"role={user.role:<10} password_hash={user.password_hash[:20]}..."
            )


if __name__ == "__main__":
    main()
