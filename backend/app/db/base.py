from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Prevent SQLAlchemy from raising during test collection when modules are imported
# multiple times in the same interpreter.
# This is critical for the test suite because both app.models.* and app.db.models.*
# define the same table names.
