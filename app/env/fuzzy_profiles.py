PROFILES = {
    "standard": dict(heat_shift=0,  air_scale=1.0, uv_scale=1.0, ve_ratio=1.0,  consequents={}),
    "asthma":   dict(heat_shift=0,  air_scale=0.7, uv_scale=1.0, ve_ratio=1.0,  consequents={"R10": "medium", "R5": "extreme"}),
    "senior":   dict(heat_shift=-3, air_scale=1.0, uv_scale=0.8, ve_ratio=0.85, consequents={"R9": "medium"}),
    "athlete":  dict(heat_shift=-2, air_scale=1.0, uv_scale=1.0, ve_ratio=1.7,  consequents={}),
}
