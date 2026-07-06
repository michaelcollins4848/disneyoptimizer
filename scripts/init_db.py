#creates all tables in postgresql
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.models import Base
from db.session import engine


def init_db():
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Done. Tables created:")
    for table in Base.metadata.tables:
        print(f"  - {table}")


if __name__ == "__main__":
    init_db()
