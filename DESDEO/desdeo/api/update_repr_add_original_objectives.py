from sqlmodel import Session
from desdeo.api.db import engine
from desdeo.api.models.problem import RepresentativeNonDominatedSolutions, ProblemDB

with Session(engine) as session:
    repr_set = session.get(RepresentativeNonDominatedSolutions, 1)
    if repr_set is None:
        print('Representative set id=1 not found')
        raise SystemExit(1)

    problem_db = session.get(ProblemDB, repr_set.metadata_instance.problem_id)
    if problem_db is None:
        print('Problem not found')
        raise SystemExit(1)

    # Build mapping of objective symbols to maximize flag
    obj_meta = {o.symbol: getattr(o, 'maximize', False) for o in problem_db.objectives}

    sd = repr_set.solution_data
    for sym, is_max in obj_meta.items():
        key_min = f"{sym}_min"
        if key_min not in sd:
            print(f"Warning: {key_min} not in solution_data")
            continue
        mincol = sd[key_min]
        # original values: invert for maximize
        orig = [(-v if is_max else v) for v in mincol]
        sd[sym] = orig

    repr_set.solution_data = sd
    session.add(repr_set)
    session.commit()
    session.refresh(repr_set)
    print('Added original objective columns to representative set solution_data')
