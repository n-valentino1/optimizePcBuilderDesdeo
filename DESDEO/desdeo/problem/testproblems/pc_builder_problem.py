"""DESDEO problem definition for the PC-builder optimization task."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from desdeo.problem.schema import (
    DiscreteRepresentation,
    Objective,
    ObjectiveTypeEnum,
    Problem,
    Variable,
    VariableTypeEnum,
)


WORKTREE_ROOT = Path(__file__).resolve().parents[4]
CUSTOM_PROJECT_DIR = WORKTREE_ROOT / "custom-gui-setup-desdeo-project"


def parse_ram_gen(speed_str: str) -> int:
    """Extract the RAM generation from a speed string."""
    speed_str = str(speed_str).upper()
    if "DDR5" in speed_str:
        return 5
    if "DDR4" in speed_str:
        return 4
    if "DDR3" in speed_str:
        return 3
    digits = "".join(ch for ch in speed_str if ch.isdigit())
    if not digits:
        return 4
    speed_num = int(digits)
    if speed_num >= 4800:
        return 5
    if speed_num >= 2133:
        return 4
    return 3


def parse_ram_cap(modules_str: str) -> int:
    """Extract the total RAM capacity in GB from a modules string."""
    modules_str = str(modules_str).upper()
    try:
        if "X" in modules_str:
            parts = modules_str.split("X")
            count = int("".join(ch for ch in parts[0] if ch.isdigit()))
            size = int("".join(ch for ch in parts[1] if ch.isdigit()))
            return count * size
        if "," in modules_str:
            count, size = modules_str.split(",")
            return int(count.strip()) * int(size.strip())
        digits = "".join(ch for ch in modules_str if ch.isdigit())
        return int(digits) if digits else 16
    except ValueError:
        return 16


def parse_ssd_cap(cap_str: str) -> float:
    """Extract the SSD capacity in GB from a capacity string."""
    cap_str = str(cap_str).upper()
    try:
        if "TB" in cap_str:
            return float(cap_str.replace("TB", "").strip()) * 1000
        return float(cap_str.replace("GB", "").strip())
    except ValueError:
        return float("nan")


def load_component_data() -> dict[str, pd.DataFrame]:
    """Load the component CSV files from the custom PC-builder project."""
    try:
        mobos = pd.read_csv(CUSTOM_PROJECT_DIR / "motherboard.csv")
        ram = pd.read_csv(CUSTOM_PROJECT_DIR / "memory.csv")
        ssds = pd.read_csv(CUSTOM_PROJECT_DIR / "internal-hard-drive.csv")
        gpus = pd.read_csv(CUSTOM_PROJECT_DIR / "video-card.csv")
        cpus = pd.read_csv(CUSTOM_PROJECT_DIR / "cpu.csv")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Could not find the PC component CSV files in {CUSTOM_PROJECT_DIR}. {exc}") from exc

    mobos = mobos.dropna(subset=["price", "socket", "max_memory"]).reset_index(drop=True)
    ram = ram.dropna(subset=["price", "speed", "modules"]).reset_index(drop=True)
    ssds = ssds.dropna(subset=["price", "capacity"]).reset_index(drop=True)
    gpus = gpus.dropna(subset=["price", "core_clock", "memory"]).reset_index(drop=True)
    cpus = cpus.dropna(subset=["price", "boost_clock", "core_clock", "core_count", "microarchitecture"]).reset_index(drop=True)

    ram["ram_gen"] = ram["speed"].apply(parse_ram_gen)
    ram["capacity_gb"] = ram["modules"].apply(parse_ram_cap)
    ram = ram.dropna(subset=["ram_gen", "capacity_gb"]).reset_index(drop=True)
    ram["ram_gen"] = ram["ram_gen"].astype(int)
    ram["capacity_gb"] = ram["capacity_gb"].astype(int)

    ssds["capacity_gb"] = ssds["capacity"].apply(parse_ssd_cap)
    ssds = ssds.dropna(subset=["capacity_gb"]).reset_index(drop=True)

    socket_to_ram_gen = {
        "AM5": 5,
        "AM4": 4,
        "LGA1700": 5,
        "LGA1200": 4,
    }
    arch_to_socket = {
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

    mobos["ram_gen"] = mobos["socket"].map(socket_to_ram_gen)
    mobos = mobos.dropna(subset=["ram_gen"]).reset_index(drop=True)
    mobos["ram_gen"] = mobos["ram_gen"].astype(int)

    cpus["socket"] = cpus["microarchitecture"].map(arch_to_socket)
    cpus = cpus.dropna(subset=["socket"]).reset_index(drop=True)
    return {"mobos": mobos, "ram": ram, "ssds": ssds, "gpus": gpus, "cpus": cpus}


def build_valid_pc_combinations(
    max_budget: float = 4000.0,
    max_points: int = 500,
    sample_size: int = 12,
) -> tuple[dict[str, list[int]], dict[str, list[float]]]:
    """Sample valid PC builds to create a manageable DESDEO discrete problem."""
    data = load_component_data()
    mobos = data["mobos"].sample(n=min(sample_size, len(data["mobos"])), random_state=42)
    ram = data["ram"].sample(n=min(sample_size, len(data["ram"])), random_state=43)
    ssds = data["ssds"].sample(n=min(sample_size, len(data["ssds"])), random_state=44)
    gpus = data["gpus"].sample(n=min(sample_size, len(data["gpus"])), random_state=45)
    cpus = data["cpus"].sample(n=min(sample_size, len(data["cpus"])), random_state=46)

    var_values = {"m": [], "r": [], "s": [], "g": [], "c": []}
    obj_values = {
        "f_1": [],
        "f_2": [],
        "f_3": [],
        "f_4": [],
        "f_5": [],
        "f_6": [],
    }

    for m_idx, m_row in mobos.iterrows():
        for r_idx, r_row in ram.iterrows():
            if r_row["ram_gen"] != m_row["ram_gen"] or r_row["capacity_gb"] > m_row["max_memory"]:
                continue
            for s_idx, s_row in ssds.iterrows():
                for g_idx, g_row in gpus.iterrows():
                    for c_idx, c_row in cpus.iterrows():
                        if c_row["socket"] != m_row["socket"]:
                            continue
                        total_price = float(m_row["price"] + r_row["price"] + s_row["price"] + g_row["price"] + c_row["price"])
                        if total_price > max_budget:
                            continue
                        var_values["m"].append(int(m_idx))
                        var_values["r"].append(int(r_idx))
                        var_values["s"].append(int(s_idx))
                        var_values["g"].append(int(g_idx))
                        var_values["c"].append(int(c_idx))
                        obj_values["f_1"].append(total_price)
                        obj_values["f_2"].append(float(c_row["boost_clock"]))
                        obj_values["f_3"].append(float(c_row["core_count"]))
                        obj_values["f_4"].append(float(g_row["memory"]))
                        obj_values["f_5"].append(float(g_row["core_clock"]))
                        obj_values["f_6"].append(float(s_row["capacity_gb"]))

                        if len(var_values["m"]) >= max_points:
                            return var_values, obj_values

    return var_values, obj_values


def pc_builder_problem() -> Problem:
    """Create the DESDEO problem representation for the PC-builder optimization task."""
    data = load_component_data()
    var_values, obj_values = build_valid_pc_combinations(max_budget=4000)
    variables = [
        Variable(
            name="motherboard index",
            symbol="m",
            variable_type=VariableTypeEnum.integer,
            lowerbound=0,
            upperbound=max(0, len(data["mobos"]) - 1),
            initial_value=0,
        ),
        Variable(
            name="RAM index",
            symbol="r",
            variable_type=VariableTypeEnum.integer,
            lowerbound=0,
            upperbound=max(0, len(data["ram"]) - 1),
            initial_value=0,
        ),
        Variable(
            name="SSD index",
            symbol="s",
            variable_type=VariableTypeEnum.integer,
            lowerbound=0,
            upperbound=max(0, len(data["ssds"]) - 1),
            initial_value=0,
        ),
        Variable(
            name="GPU index",
            symbol="g",
            variable_type=VariableTypeEnum.integer,
            lowerbound=0,
            upperbound=max(0, len(data["gpus"]) - 1),
            initial_value=0,
        ),
        Variable(
            name="CPU index",
            symbol="c",
            variable_type=VariableTypeEnum.integer,
            lowerbound=0,
            upperbound=max(0, len(data["cpus"]) - 1),
            initial_value=0,
        ),
    ]

    # Build objectives and compute ideal/nadir from the sampled objective values
    obj_specs = [
        ("Total price", "f_1", False, "USD"),
        ("CPU boost clock", "f_2", True, "GHz"),
        ("CPU core count", "f_3", True, "count"),
        ("GPU VRAM", "f_4", True, "MB"),
        ("GPU core clock", "f_5", True, "MHz"),
        ("SSD capacity", "f_6", True, "GB"),
    ]

    objectives = []
    for name, symbol, maximize, unit in obj_specs:
        vals = obj_values.get(symbol, [])
        # filter out NaNs if present
        clean_vals = [v for v in vals if v == v]
        if len(clean_vals) == 0:
            ideal = None
            nadir = None
        else:
            if maximize:
                ideal = float(max(clean_vals))
                nadir = float(min(clean_vals))
            else:
                ideal = float(min(clean_vals))
                nadir = float(max(clean_vals))

        objectives.append(
            Objective(
                name=name,
                symbol=symbol,
                func=None,
                objective_type=ObjectiveTypeEnum.data_based,
                maximize=maximize,
                ideal=ideal,
                nadir=nadir,
                unit=unit,
            )
        )

    discrete_representation = DiscreteRepresentation(
        variable_values={
            "m": var_values["m"],
            "r": var_values["r"],
            "s": var_values["s"],
            "g": var_values["g"],
            "c": var_values["c"],
        },
        objective_values=obj_values,
    )

    return Problem(
        name="PC builder optimization",
        description=(
            "A multi-objective PC-part selection problem that minimizes total build cost while maximizing "
            "CPU/GPU performance and SSD capacity. Valid combinations are filtered for motherboard/CPU "
            "socket compatibility and compatible RAM generations and capacities."
        ),
        variables=variables,
        objectives=objectives,
        discrete_representation=discrete_representation,
    )
