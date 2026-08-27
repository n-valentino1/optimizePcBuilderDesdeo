from sqlmodel import Session
from desdeo.api.db import engine
from desdeo.api.models.problem import RepresentativeNonDominatedSolutions, ProblemDB

with Session(engine) as session:
    # Get the representative set we just added
    repr_set = session.get(RepresentativeNonDominatedSolutions, 1)
    if repr_set is None:
        print('Representative set id=1 not found')
        raise SystemExit(1)

    # Get the problem to access objective names and discrete_representation
    problem_db = session.get(ProblemDB, repr_set.metadata_instance.problem_id)
    if problem_db is None:
        print('Problem not found')
        raise SystemExit(1)

    dr = problem_db.discrete_representation
    if dr is None:
        print('No discrete rep')
        raise SystemExit(1)

    obj_values = dr.objective_values or {}

    # Add objective columns without _min (original values)
    for sym, vals in obj_values.items():
        repr_set.solution_data[sym] = [float(v) for v in vals]

    session.add(repr_set)
    session.commit()
    session.refresh(repr_set)

    print('Updated representative set with objective columns:', list(obj_values.keys()))
