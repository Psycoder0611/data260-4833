import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root@localhost/s4833_rel"
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True
)

db_session_basede26 = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    db = db_session_basede26()

    try:
        yield db
    finally:
        db.close()