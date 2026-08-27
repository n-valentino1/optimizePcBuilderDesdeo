from sqlmodel import Session, select

from desdeo.api.db import engine
from desdeo.api.models.problem import ProblemDB, ProblemMetaDataDB, RepresentativeNonDominatedSolutions

PROBLEM_NAME = "PC builder optimization"


with Session(engine) as session:
    stmt = select(ProblemDB).where(ProblemDB.name == PROBLEM_NAME)
    problem_db = session.exec(stmt).first()
    if not problem_db:
        print(f"Problem named '{PROBLEM_NAME}' not found. Exiting.")
        raise SystemExit(1)

    dr = problem_db.discrete_representation
    if dr is None:
        print("Problem has no discrete representation. Exiting.")
        raise SystemExit(1)

    # ensure the representative set contains both original objective columns and the
    # minimized versions that the E-NAUTILUS implementation expects.
    var_values = dr.variable_values or {}
    obj_values = dr.objective_values or {}
    obj_meta = {o.symbol: o for o in problem_db.objectives}

    solution_data = {sym: list(vals) for sym, vals in var_values.items()}
    ideal = {}
    nadir = {}

    for sym, vals in obj_values.items():
        values = [float(v) for v in vals]
        meta = obj_meta.get(sym)
        is_max = bool(getattr(meta, "maximize", False))

        # keep original values for generic usage and objective-space queries
        solution_data[sym] = values

        # convert to minimization coordinates expected by E-NAUTILUS internals
        transformed = [-v if is_max else v for v in values]
        solution_data[f"{sym}_min"] = transformed

        # store the original-sense ideal and nadir so the Problem metadata remains meaningful
        ideal[sym] = float(max(values)) if is_max else float(min(values))
        nadir[sym] = float(min(values)) if is_max else float(max(values))

    if problem_db.problem_metadata is None:
        pm = ProblemMetaDataDB(problem_id=problem_db.id, problem=problem_db)
        session.add(pm)
        session.commit()
        session.refresh(pm)
        metadata_id = pm.id
        metadata_instance = pm
    else:
        metadata_id = problem_db.problem_metadata.id
        metadata_instance = problem_db.problem_metadata

    existing = session.exec(
        select(RepresentativeNonDominatedSolutions).where(
            RepresentativeNonDominatedSolutions.metadata_id == metadata_id
        )
    ).first()

    if existing is None:
        repr_set = RepresentativeNonDominatedSolutions(
            metadata_id=metadata_id,
            name="Default non-dominated set",
            description="Representative set generated from discrete representation.",
            solution_data=solution_data,
            ideal=ideal,
            nadir=nadir,
            metadata_instance=metadata_instance,
        )
        session.add(repr_set)
        print(f"Added representative set for problem id={problem_db.id}.")
    else:
        existing.solution_data = solution_data
        existing.ideal = ideal
        existing.nadir = nadir
        existing.name = "Default non-dominated set"
        existing.description = "Representative set generated from discrete representation."
        repr_set = existing
        print(f"Updated representative set id={repr_set.id} for problem id={problem_db.id}.")

    session.commit()
    session.refresh(repr_set)
    print(f"Representative set id={repr_set.id} has keys: {list(solution_data.keys())[:20]}")
