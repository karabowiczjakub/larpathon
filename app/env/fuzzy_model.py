import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl

HEAT_U = np.arange(-30, 50.01, 0.5)
AIR_U = np.arange(0, 6.001, 0.02)
UV_U = np.arange(0, 12.001, 0.05)
OUT_U = np.arange(0, 10.001, 0.05)

def build_system(p: dict) -> ctrl.ControlSystem:
    heat = ctrl.Antecedent(HEAT_U, "heat")
    air = ctrl.Antecedent(AIR_U, "air")
    uv = ctrl.Antecedent(UV_U, "uv")
    out = ctrl.Consequent(OUT_U, "discomfort", defuzzify_method="centroid")
    
    hs, ak, uk = p["heat_shift"], p["air_scale"], p["uv_scale"]
    heat["cold"] = fuzz.trapmf(HEAT_U, [-30, -30, 0 + hs, 9 + hs])
    heat["comfortable"] = fuzz.trapmf(HEAT_U, [0 + hs, 9 + hs, 22 + hs, 26 + hs])
    heat["warm"] = fuzz.trapmf(HEAT_U, [22 + hs, 26 + hs, 30 + hs, 32 + hs])
    heat["hot"] = fuzz.trapmf(HEAT_U, [28 + hs, 32 + hs, 36 + hs, 38 + hs])
    heat["very_hot"] = fuzz.trapmf(HEAT_U, [36 + hs, 38 + hs, 50, 50])
    
    air["good"] = fuzz.trapmf(AIR_U, [0, 0, 1 * ak, 1.8 * ak])
    air["fair"] = fuzz.trimf(AIR_U, [1 * ak, 2 * ak, 3 * ak])
    air["poor"] = fuzz.trapmf(AIR_U, [2.5 * ak, 3.5 * ak, 4.5 * ak, 5 * ak])
    air["very_poor"] = fuzz.trapmf(AIR_U, [4.5 * ak, 5.5 * ak, 6, 6])
    
    uv["low"] = fuzz.trapmf(UV_U, [0, 0, 2 * uk, 3 * uk])
    uv["moderate"] = fuzz.trimf(UV_U, [2 * uk, 4 * uk, 6 * uk])
    uv["high"] = fuzz.trapmf(UV_U, [5 * uk, 6 * uk, 7 * uk, 8 * uk])
    uv["very_high"] = fuzz.trapmf(UV_U, [7 * uk, 8.5 * uk, 12, 12])
    
    out["none"] = fuzz.trapmf(OUT_U, [0, 0, 1, 2])
    out["low"] = fuzz.trimf(OUT_U, [1, 2.5, 4])
    out["medium"] = fuzz.trimf(OUT_U, [3, 5, 7])
    out["high"] = fuzz.trimf(OUT_U, [6, 7.5, 9])
    out["extreme"] = fuzz.trapmf(OUT_U, [8, 9, 10, 10])

    heat_ok = heat["comfortable"]
    heat_mild = heat["warm"] | heat["cold"]
    heat_le_mild = heat["comfortable"] | heat["warm"] | heat["cold"]
    air_le_fair = air["good"] | air["fair"]
    uv_ok = uv["low"] | uv["moderate"]
    uv_le_high = uv["low"] | uv["moderate"] | uv["high"]
    c = p["consequents"]
    
    return ctrl.ControlSystem([
        ctrl.Rule(air["very_poor"] | heat["very_hot"], out["extreme"]),                     # R1
        ctrl.Rule(air["poor"] & (heat["hot"] | uv["very_high"]), out["extreme"]),           # R2
        ctrl.Rule(heat["hot"] & uv["very_high"], out["extreme"]),                           # R3
        ctrl.Rule(heat["hot"] & air_le_fair & uv_le_high, out["high"]),                     # R4
        ctrl.Rule(air["poor"] & heat_le_mild & uv_le_high, out[c.get("R5", "high")]),       # R5
        ctrl.Rule(uv["very_high"] & heat_le_mild & air_le_fair, out["high"]),               # R6
        ctrl.Rule(uv["high"] & heat_le_mild & air_le_fair, out["medium"]),                  # R7
        ctrl.Rule(heat_mild & air["fair"] & uv_ok, out["medium"]),                          # R8
        ctrl.Rule(heat_mild & air["good"] & uv_ok, out[c.get("R9", "low")]),                # R9
        ctrl.Rule(air["fair"] & heat_ok & uv_ok, out[c.get("R10", "low")]),                 # R10
        ctrl.Rule(air["good"] & heat_ok & uv_ok, out["none"]),                              # R11
    ])
