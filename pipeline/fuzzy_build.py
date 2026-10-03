from pathlib import Path

import numpy as np
from joblib import Parallel, delayed
from skfuzzy import control as ctrl

from app.env.fuzzy_model import build_system
from app.env.fuzzy_profiles import PROFILES

OUT = Path(__file__).resolve().parents[1] / "data" / "processed"
G_HEAT = np.arange(-30, 50.01, 2.0)
G_AIR = np.arange(0, 6.001, 0.2)
G_UV = np.arange(0, 12.001, 1.0)

def monotone(lut, heat_grid, comfort_hi=22.0):
    out = np.maximum.accumulate(lut, axis=1)                       # air ↑
    out = np.maximum.accumulate(out, axis=2)                       # uv ↑
    hot = heat_grid >= comfort_hi
    out[hot] = np.maximum.accumulate(out[hot], axis=0)             # upał ↑
    out[~hot] = np.maximum.accumulate(out[~hot][::-1], axis=0)[::-1]   # mróz ↓
    return out

def slab(p, h):
    sim = ctrl.ControlSystemSimulation(build_system(p), cache=False)
    row = np.full((len(G_AIR), len(G_UV)), np.nan, np.float32)
    for j, a in enumerate(G_AIR):
        for k, u in enumerate(G_UV):
            sim.input["heat"], sim.input["air"], sim.input["uv"] = h, a, u
            try:
                sim.compute()
                row[j, k] = sim.output["discomfort"]
            except (ValueError, KeyError):
                pass
    return row

def build_fuzzy():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, p in PROFILES.items():
        print(f"Building fuzzy LUT for {name}...")
        lut = np.stack(Parallel(n_jobs=-1)(delayed(slab)(p, h) for h in G_HEAT))
        assert not np.isnan(lut).any(), f"{name}: luka w regułach"
        np.save(OUT / f"lut_{name}.npy", monotone(lut, G_HEAT, 22 + p["heat_shift"]))
        print(name, "ok")
    np.savez(OUT / "lut_grid.npz", heat=G_HEAT, air=G_AIR, uv=G_UV)

if __name__ == "__main__":
    build_fuzzy()
