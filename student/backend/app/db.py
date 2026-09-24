import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL

engine = create_engine(
    URL.create(
        "postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ.get("POSTGRES_HOST", "db"),
        database=os.environ["POSTGRES_DB"],
    ),
    pool_pre_ping=True,
    hide_parameters=True,
    pool_size=5,
    max_overflow=5,
    connect_args={"connect_timeout": 3},
)
