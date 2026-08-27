"""Initialize the database with the custom PC-builder DESDEO problem."""

from __future__ import annotations

import warnings

from sqlalchemy_utils import database_exists
from sqlmodel import Session, SQLModel

from desdeo.api.config import ServerConfig, SettingsConfig
from desdeo.api.db import engine
from desdeo.api.models import ProblemDB, User, UserRole
from desdeo.api.routers.user_authentication import get_password_hash
from desdeo.problem.testproblems.pc_builder_problem import pc_builder_problem


if __name__ == "__main__":
    if SettingsConfig.debug:
        print("Creating database tables.")
        if not database_exists(engine.url):
            SQLModel.metadata.create_all(engine)
        else:
            warnings.warn("Database already exists. Clearing it.", stacklevel=1)
            SQLModel.metadata.reflect(bind=engine)
            SQLModel.metadata.drop_all(bind=engine)
            SQLModel.metadata.create_all(engine)
        print("Database tables created.")

        with Session(engine) as session:
            user_guest = User(
                username="guest",
                password_hash=get_password_hash("guest"),
                role=UserRole.guest,
                group="guest",
            )
            session.add(user_guest)
            session.commit()
            session.refresh(user_guest)

            user_analyst = User(
                username=ServerConfig.test_user_analyst_name,
                password_hash=get_password_hash(ServerConfig.test_user_analyst_password),
                role=UserRole.analyst,
                group="test",
            )
            session.add(user_analyst)
            session.commit()
            session.refresh(user_analyst)

            problem = pc_builder_problem()
            db_problem = ProblemDB.from_problem(problem, user_guest)
            session.add(db_problem)
            session.commit()
            session.refresh(db_problem)
            print(f"PC builder problem added to the database for the guest user (id={db_problem.id}).")
    else:
        print("Database initialization is only enabled when SettingsConfig.debug is True.")
