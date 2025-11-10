from sqlmodel import SQLModel, create_engine, Session
from os import getenv

DATABASE_URL = getenv("DATABASE_URL", "sqlite+aiosqlite:///./standout.db")

# For synchronous SQLModel operations in startup seed we can still use sqlite:/// (sync).
SYNC_DATABASE_URL = getenv("SYNC_DATABASE_URL", "sqlite:///./standout.db")

# Async engine would require async session setup; to keep it simple, use sync Session per request.
engine = create_engine(SYNC_DATABASE_URL, echo=False)

def init_db():
    from . import models  # noqa
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
