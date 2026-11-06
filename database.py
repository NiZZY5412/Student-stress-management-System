from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# DEFAULT CONNECTION STRING - PLEASE UPDATE 'server_name' if different.
# Format: mssql+pyodbc://username:password@server_name/database_name?driver=ODBC+Driver+17+for+SQL+Server
# For Windows Auth (Trusted Connection), simple format usually works if driver is installed:
# SQLALCHEMY_DATABASE_URL = "mssql+pyodbc://@./SSMCS_DB?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"

# Ideally, read from environment variable
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "mssql+pyodbc://@localhost/SSMCS_DB?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
