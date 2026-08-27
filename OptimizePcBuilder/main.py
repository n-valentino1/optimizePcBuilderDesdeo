"""Single-file PC builder and DESDEO integration.

This keeps the project simple and readable:
- the actual optimization logic is here
- the DESDEO conversion code is also here
- there is only one Python file in the custom project repo

The official DESDEO browser UI still comes from the sparate DESDEO GitHub repo.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import ElementwiseProblem
from pymoo.optimize import minimize
from sklearn.preprocessing import MinMaxScaler

try:
    import polars as pl
    from pymoo.util.nds.non_dominated_sorting import find_non_dominated
    from desdeo.problem.schema import DiscreteRepresentation, Objective, Problem, Variable
    from desdeo.mcdm.enautilus import enautilus_get_representative_solutions, enautilus_step

    DESDEO_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency for the browser GUI
    pl = None
    find_non_dominated = None
    DiscreteRepresentation = None
    Objective = None
    Problem = None
    Variable = None
    enautilus_get_representative_solutions = None
    enautilus_step = None
    DESDEO_AVAILABLE = False

DATA_DIR = Path(__file__).resolve().parent / "data"


# ---------------------------------------------------------------------------
# Data loading and cleaning
# ---------------------------------------------------------------------------
def load_component_data():
    """Read the CSV files for all PC parts from the project data folder."""
    try:
        motherboards = pd.read_csv(DATA_DIR / "motherboard.csv")
        ram = pd.read_csv(DATA_DIR / "memory.csv")
        ssds = pd.read_csv(DATA_DIR / "internal-hard-drive.csv")
        gpus = pd.read_csv(DATA_DIR / "video-card.csv")
        cpus = pd.read_csv(DATA_DIR / "cpu.csv")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Could not find one of the CSV files in {DATA_DIR}: {exc}") from exc

    motherboards = motherboards.dropna(subset=["price", "socket", "max_memory"]).reset_index(drop=True)
    ram = ram.dropna(subset=["price", "speed", "modules"]).reset_index(drop=True)
    ssds = ssds.dropna(subset=["price", "capacity"]).reset_index(drop=True)
    gpus = gpus.dropna(subset=["price", "core_clock", "memory"]).reset_index(drop=True)
    cpus = cpus.dropna(subset=["price", "boost_clock", "core_clock", "core_count", "microarchitecture"]).reset_index(drop=True)

    return {
        "motherboards": motherboards,
        "ram": ram,
        "ssds": ssds,
        "gpus": gpus,
        "cpus": cpus,
    }


def parse_ram_generation(speed_text):
    """Turn a RAM speed string like DDR4-3200 into a simple generation value."""
    speed_text = str(speed_text).upper()
    if "DDR5" in speed_text:
        return 5
    if "DDR4" in speed_text:
        return 4
    if "DDR3" in speed_text:
        return 3

    digits = "".join(ch for ch in speed_text if ch.isdigit())
    if not digits:
        return 4

    number = int(digits)
    if number >= 4800:
        return 5
    if number >= 2133:
        return 4
    return 3


def parse_ram_capacity(module_text):
    """Turn a RAM string like 2x16GB into a total size in GB."""
    try:
        module_text = str(module_text).upper()
        if "X" in module_text:
            parts = module_text.split("X")
            count = int("".join(ch for ch in parts[0] if ch.isdigit()))
            size = int("".join(ch for ch in parts[1] if ch.isdigit()))
            return count * size
        if "," in module_text:
            count, size = module_text.split(",")
            return int(count.strip()) * int(size.strip())
        return int("".join(ch for ch in module_text if ch.isdigit()))
    except Exception:
        return 16


def parse_ssd_capacity(capacity_text):
    """Turn a string like 2TB or 512GB into a number in GB."""
    try:
        capacity_text = str(capacity_text).upper()
        if "TB" in capacity_text:
            return float(capacity_text.replace("TB", "").strip()) * 1000
        return float(capacity_text.replace("GB", "").strip())
    except Exception:
        return np.nan


def prepare_data_for_model():
    """Clean everything and make the part tables easier to compare."""
    data = load_component_data()

    motherboards = data["motherboards"]
    ram = data["ram"]
    ssds = data["ssds"]
    gpus = data["gpus"]
    cpus = data["cpus"]

    ram["ram_gen"] = ram["speed"].apply(parse_ram_generation)
    ram["capacity_gb"] = ram["modules"].apply(parse_ram_capacity)
    ram = ram.dropna(subset=["ram_gen", "capacity_gb"]).reset_index(drop=True)
    ram["ram_gen"] = ram["ram_gen"].astype(int)
    ram["capacity_gb"] = ram["capacity_gb"].astype(int)

    ssds["capacity_gb"] = ssds["capacity"].apply(parse_ssd_capacity)
    ssds = ssds.dropna(subset=["capacity_gb"]).reset_index(drop=True)

    socket_to_ram_gen = {"AM5": 5, "AM4": 4, "LGA1700": 5, "LGA1200": 4}
    architecture_to_socket = {
        "Zen 5": "AM5",
        "Zen 4": "AM5",
        "Zen 3": "AM4",
        "Zen 2": "AM4",
        "Zen": "AM4",
        "Raptor Lake": "LGA1700",
        "Alder Lake": "LGA1700",
        "Rocket Lake": "LGA1200",
        "Comet Lake": "LGA1200",
    }

    motherboards["ram_gen"] = motherboards["socket"].map(socket_to_ram_gen)
    motherboards = motherboards.dropna(subset=["ram_gen"]).reset_index(drop=True)
    motherboards["ram_gen"] = motherboards["ram_gen"].astype(int)

    cpus["socket"] = cpus["microarchitecture"].map(architecture_to_socket)
    cpus = cpus.dropna(subset=["socket"]).reset_index(drop=True)

    scaler = MinMaxScaler()
    cpus["scaled_clk"] = scaler.fit_transform(cpus[["boost_clock"]])
    cpus["scaled_cores"] = scaler.fit_transform(cpus[["core_count"]])
    gpus["scaled_mem"] = scaler.fit_transform(gpus[["memory"]])
    gpus["scaled_clk"] = scaler.fit_transform(gpus[["core_clock"]])
    ssds["scaled_cap"] = scaler.fit_transform(ssds[["capacity_gb"]])

    return {
        "motherboards": motherboards,
        "ram": ram,
        "ssds": ssds,
        "gpus": gpus,
        "cpus": cpus,
    }


# ---------------------------------------------------------------------------
# Pymoo model
# ---------------------------------------------------------------------------
class PCBuilder(ElementwiseProblem):
    """Choose one motherboard, RAM stick, SSD, GPU, and CPU."""

    def __init__(self, data, max_budget=4000, min_ram_gb=16, min_cores=5, min_vram=11, min_ssd_gb=900):
        self.data = data
        self.motherboards = data["motherboards"]
        self.ram = data["ram"]
        self.ssds = data["ssds"]
        self.gpus = data["gpus"]
        self.cpus = data["cpus"]

        self.max_budget = max_budget
        self.min_ram_gb = min_ram_gb
        self.min_cores = min_cores
        self.min_vram = min_vram
        self.min_ssd_gb = min_ssd_gb

        super().__init__(
            n_var=5,
            xl=np.zeros(5),
            xu=np.array([
                len(self.motherboards) - 1,
                len(self.ram) - 1,
                len(self.ssds) - 1,
                len(self.gpus) - 1,
                len(self.cpus) - 1,
            ]),
            n_obj=6,
            n_ieq_constr=8,
        )

    def _evaluate(self, x, out, *args, **kwargs):
        m_idx = int(np.round(x[0]))
        r_idx = int(np.round(x[1]))
        s_idx = int(np.round(x[2]))
        g_idx = int(np.round(x[3]))
        c_idx = int(np.round(x[4]))

        total_price = (
            self.motherboards.loc[m_idx, "price"]
            + self.ram.loc[r_idx, "price"]
            + self.ssds.loc[s_idx, "price"]
            + self.gpus.loc[g_idx, "price"]
            + self.cpus.loc[c_idx, "price"]
        )

        cpu_clock_scaled = self.cpus.loc[c_idx, "scaled_clk"]
        cpu_cores_scaled = self.cpus.loc[c_idx, "scaled_cores"]
        gpu_clock_scaled = self.gpus.loc[g_idx, "scaled_clk"]
        gpu_memory_scaled = self.gpus.loc[g_idx, "scaled_mem"]
        ssd_capacity_scaled = self.ssds.loc[s_idx, "scaled_cap"]

        socket_ok = 0 if self.motherboards.loc[m_idx, "socket"] == self.cpus.loc[c_idx, "socket"] else 1
        ram_ok = 0 if self.ram.loc[r_idx, "ram_gen"] == self.motherboards.loc[m_idx, "ram_gen"] else 1
        memory_limit = self.ram.loc[r_idx, "capacity_gb"] - self.motherboards.loc[m_idx, "max_memory"]
        min_ram = self.min_ram_gb - self.ram.loc[r_idx, "capacity_gb"]
        min_cores = self.min_cores - self.cpus.loc[c_idx, "core_count"]
        min_vram = self.min_vram - self.gpus.loc[g_idx, "memory"]
        min_ssd = self.min_ssd_gb - self.ssds.loc[s_idx, "capacity_gb"]

        out["F"] = [
            total_price,
            -cpu_clock_scaled,
            -cpu_cores_scaled,
            -gpu_memory_scaled,
            -gpu_clock_scaled,
            -ssd_capacity_scaled,
        ]

        out["G"] = [
            total_price - self.max_budget,
            socket_ok,
            ram_ok,
            memory_limit,
            min_ram,
            min_cores,
            min_vram,
            min_ssd,
        ]


# ---------------------------------------------------------------------------
# Solving and building a results table
# ---------------------------------------------------------------------------
def run_pareto_search(data, max_budget=4000, min_ram_gb=16, min_cores=5, min_vram=11, min_ssd_gb=900, n_gen=250, pop_size=250):
    """Run NSGA-II and return the full Pareto front."""
    problem = PCBuilder(
        data,
        max_budget=max_budget,
        min_ram_gb=min_ram_gb,
        min_cores=min_cores,
        min_vram=min_vram,
        min_ssd_gb=min_ssd_gb,
    )
    algorithm = NSGA2(pop_size=pop_size)

    result = minimize(
        problem,
        algorithm,
        termination=("n_gen", n_gen),
        seed=1,
        verbose=False,
    )
    return result


def build_results_table(result, data):
    """Turn the optimizer output into a simple pandas table of builds."""
    rows = []
    motherboards = data["motherboards"]
    ram = data["ram"]
    ssds = data["ssds"]
    gpus = data["gpus"]
    cpus = data["cpus"]

    for x_values, objective_values in zip(result.X, result.F):
        m_idx = int(np.clip(round(x_values[0]), 0, len(motherboards) - 1))
        r_idx = int(np.clip(round(x_values[1]), 0, len(ram) - 1))
        s_idx = int(np.clip(round(x_values[2]), 0, len(ssds) - 1))
        g_idx = int(np.clip(round(x_values[3]), 0, len(gpus) - 1))
        c_idx = int(np.clip(round(x_values[4]), 0, len(cpus) - 1))

        row = {
            "motherboard": motherboards.loc[m_idx, "name"],
            "ram": ram.loc[r_idx, "name"],
            "ssd": ssds.loc[s_idx, "name"],
            "gpu": gpus.loc[g_idx, "name"],
            "cpu": cpus.loc[c_idx, "name"],
            "total_price": float(objective_values[0]),
            "cpu_clock": float(cpus.loc[c_idx, "boost_clock"]),
            "cpu_cores": float(cpus.loc[c_idx, "core_count"]),
            "gpu_vram": float(gpus.loc[g_idx, "memory"]),
            "gpu_clock": float(gpus.loc[g_idx, "core_clock"]),
            "ssd_capacity_gb": float(ssds.loc[s_idx, "capacity_gb"]),
        }
        rows.append(row)

    return pd.DataFrame(rows)


def solve_pc_builder(max_budget=4000, min_ram_gb=16, min_cores=5, min_vram=11, min_ssd_gb=900, n_gen=120, pop_size=120):
    """Public helper that runs the local optimization and returns a ready-to-read build table."""
    data = prepare_data_for_model()
    result = run_pareto_search(
        data,
        max_budget=max_budget,
        min_ram_gb=min_ram_gb,
        min_cores=min_cores,
        min_vram=min_vram,
        min_ssd_gb=min_ssd_gb,
        n_gen=n_gen,
        pop_size=pop_size,
    )
    return build_results_table(result, data)


# ---------------------------------------------------------------------------
# DESDEO conversion and E-NAUTILUS helpers
# ---------------------------------------------------------------------------
OBJECTIVE_LABELS = {
    "f_1": "Price",
    "f_2": "-CPU Clock",
    "f_3": "-CPU Cores",
    "f_4": "-GPU VRAM",
    "f_5": "-GPU Clock",
    "f_6": "-SSD Size",
}


def create_front_table(result, data):
    """Turn the pymoo Pareto front into a DESDEO-friendly table."""
    if not DESDEO_AVAILABLE:
        raise RuntimeError("DESDEO is not installed in this environment.")

    rows = []
    motherboards = data["motherboards"]
    ram = data["ram"]
    ssds = data["ssds"]
    gpus = data["gpus"]
    cpus = data["cpus"]

    for x_values, objective_values in zip(result.X, result.F):
        m_idx = int(np.clip(round(x_values[0]), 0, len(motherboards) - 1))
        r_idx = int(np.clip(round(x_values[1]), 0, len(ram) - 1))
        s_idx = int(np.clip(round(x_values[2]), 0, len(ssds) - 1))
        g_idx = int(np.clip(round(x_values[3]), 0, len(gpus) - 1))
        c_idx = int(np.clip(round(x_values[4]), 0, len(cpus) - 1))

        rows.append({
            "x_mobo": m_idx,
            "x_ram": r_idx,
            "x_ssd": s_idx,
            "x_gpu": g_idx,
            "x_cpu": c_idx,
            "f_1": float(objective_values[0]),
            "f_2": float(objective_values[1]),
            "f_3": float(objective_values[2]),
            "f_4": float(objective_values[3]),
            "f_5": float(objective_values[4]),
            "f_6": float(objective_values[5]),
        })

    front_df = pl.DataFrame(rows).unique(subset=["f_1", "f_2", "f_3", "f_4", "f_5", "f_6"])
    front_df = front_df.with_columns([
        pl.col("f_1").alias("f_1_min"),
        pl.col("f_2").alias("f_2_min"),
        pl.col("f_3").alias("f_3_min"),
        pl.col("f_4").alias("f_4_min"),
        pl.col("f_5").alias("f_5_min"),
        pl.col("f_6").alias("f_6_min"),
    ])
    return front_df


def build_desdeo_problem(front_df, data):
    """Wrap the front in a DESDEO Problem object."""
    if not DESDEO_AVAILABLE:
        raise RuntimeError("DESDEO is not installed in this environment.")

    discrete_definition = DiscreteRepresentation(
        variable_values={
            "x_mobo": front_df["x_mobo"].to_list(),
            "x_ram": front_df["x_ram"].to_list(),
            "x_ssd": front_df["x_ssd"].to_list(),
            "x_gpu": front_df["x_gpu"].to_list(),
            "x_cpu": front_df["x_cpu"].to_list(),
        },
        objective_values={
            "f_1": front_df["f_1"].to_list(),
            "f_2": front_df["f_2"].to_list(),
            "f_3": front_df["f_3"].to_list(),
            "f_4": front_df["f_4"].to_list(),
            "f_5": front_df["f_5"].to_list(),
            "f_6": front_df["f_6"].to_list(),
        },
    )

    variables = [
        Variable(name="Motherboard", symbol="x_mobo", variable_type="integer", lowerbound=0, upperbound=len(data["motherboards"]) - 1, initial_value=0),
        Variable(name="RAM", symbol="x_ram", variable_type="integer", lowerbound=0, upperbound=len(data["ram"]) - 1, initial_value=0),
        Variable(name="SSD", symbol="x_ssd", variable_type="integer", lowerbound=0, upperbound=len(data["ssds"]) - 1, initial_value=0),
        Variable(name="GPU", symbol="x_gpu", variable_type="integer", lowerbound=0, upperbound=len(data["gpus"]) - 1, initial_value=0),
        Variable(name="CPU", symbol="x_cpu", variable_type="integer", lowerbound=0, upperbound=len(data["cpus"]) - 1, initial_value=0),
    ]

    objectives = [
        Objective(name="Price", symbol="f_1", maximize=False),
        Objective(name="-CPU Clock", symbol="f_2", maximize=False),
        Objective(name="-CPU Cores", symbol="f_3", maximize=False),
        Objective(name="-GPU VRAM", symbol="f_4", maximize=False),
        Objective(name="-GPU Clock", symbol="f_5", maximize=False),
        Objective(name="-SSD Size", symbol="f_6", maximize=False),
    ]

    return Problem(
        name="PC Builder",
        description="Discrete approximation from the NSGA2 run",
        variables=variables,
        objectives=objectives,
        discrete_representation=discrete_definition,
    )


def compute_nadir_point(non_dominated_df):
    """Find a rough nadir point from the front."""
    return {
        "f_1": float(non_dominated_df["f_1"].max()),
        "f_2": float(non_dominated_df["f_2"].max()),
        "f_3": float(non_dominated_df["f_3"].max()),
        "f_4": float(non_dominated_df["f_4"].max()),
        "f_5": float(non_dominated_df["f_5"].max()),
        "f_6": float(non_dominated_df["f_6"].max()),
    }


def convert_to_readable_table(raw_results, intermediate_point=True):
    """Turn method output into a clean pandas table."""
    if intermediate_point:
        table = pd.DataFrame(raw_results.intermediate_points)
    else:
        table = pd.DataFrame(raw_results.optimal_objectives)

    table = table.rename(columns=OBJECTIVE_LABELS)
    table.index.name = "Solution ID"
    return table


def get_chosen_point(table, chosen_index):
    """Take one selected row and return it as objective-value dictionary."""
    return {
        "f_1": float(table.loc[chosen_index, "Price"]),
        "f_2": float(table.loc[chosen_index, "-CPU Clock"]),
        "f_3": float(table.loc[chosen_index, "-CPU Cores"]),
        "f_4": float(table.loc[chosen_index, "-GPU VRAM"]),
        "f_5": float(table.loc[chosen_index, "-GPU Clock"]),
        "f_6": float(table.loc[chosen_index, "-SSD Size"]),
    }


def run_enautilus(problem, non_dominated_df):
    """Run the interactive E-NAUTILUS loop."""
    if not DESDEO_AVAILABLE:
        raise RuntimeError("DESDEO is not installed in this environment.")

    total_iterations = 3
    current_iteration = 0
    selected_point = compute_nadir_point(non_dominated_df)
    reachable_indices = list(range(len(non_dominated_df)))

    while current_iteration < total_iterations:
        print(f"\n--- Round {current_iteration + 1} ---")
        result = enautilus_step(
            problem=problem,
            non_dominated_points=non_dominated_df,
            current_iteration=current_iteration,
            iterations_left=total_iterations - current_iteration,
            selected_point=selected_point,
            reachable_point_indices=reachable_indices,
            number_of_intermediate_points=4,
        )

        table = convert_to_readable_table(result)
        print("Which solution do you prefer?")
        print(table)

        chosen_index = int(input(f"Pick a Solution ID (0-{len(table) - 1}): "))
        selected_point = get_chosen_point(table, chosen_index)
        reachable_indices = result.reachable_point_indices[chosen_index]
        current_iteration += 1

    final_table = convert_to_readable_table(result)
    final_choice = int(input(f"Pick the final build (0-{len(final_table) - 1}): "))
    representative_solutions = enautilus_get_representative_solutions(problem, result, non_dominated_df)
    final_solution = representative_solutions[final_choice]
    final_readable = convert_to_readable_table(final_solution, intermediate_point=False)

    print("\nFinal chosen solution:")
    print(final_readable)
    return final_solution


def run_desdeo_workflow(data):
    """Run the full NSGA-II -> DESDEO -> E-NAUTILUS pipeline."""
    if not DESDEO_AVAILABLE:
        raise RuntimeError("DESDEO is not installed in this environment.")

    optimization_result = run_pareto_search(data)
    front_df = create_front_table(optimization_result, data)

    pareto_values = front_df.select(["f_1", "f_2", "f_3", "f_4", "f_5", "f_6"]).to_numpy()
    non_dominated_indices = find_non_dominated(pareto_values)
    non_dominated_df = front_df[non_dominated_indices, :]

    decision_problem = build_desdeo_problem(non_dominated_df, data)
    final_solution = run_enautilus(decision_problem, non_dominated_df)
    return final_solution, non_dominated_df, decision_problem


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    """Run a quick local optimization example."""
    results = solve_pc_builder(
        max_budget=4000,
        min_ram_gb=16,
        min_cores=5,
        min_vram=11,
        min_ssd_gb=900,
        n_gen=120,
        pop_size=120,
    )

    print(results.head(10).to_string(index=False))

    if DESDEO_AVAILABLE:
        print("\nDESDEO is available. Use the official DESDEO browser GUI from the separate DESDEO repo.")
    else:
        print("\nDESDEO is not installed here. The local optimization still works. Install the official DESDEO repo to use the browser GUI.")


if __name__ == "__main__":
    main()
