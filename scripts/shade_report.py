"""Export the prepared network's 14:00 / 18:30 shade comparison and statistics."""

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from app.shade.model import ShadeModel


def write_report(
    data_dir: str | Path,
    output: str | Path,
    *,
    date: str = "2025-07-03",
    bbox: tuple | None = None,
    label: str = "Prepared network",
) -> dict:
    data_dir, output = Path(data_dir), Path(output)
    edges = gpd.read_parquet(data_dir / "edges.parquet")
    model = ShadeModel.load(data_dir, len(edges))
    if bbox is not None:
        west, south, east, north = bbox
        edges = edges.to_crs(4326).cx[west:east, south:north]
    edges = edges.to_crs(2180)
    lengths = edges.geometry.length.to_numpy()
    if not len(edges) or not np.isfinite(lengths).all() or lengths.sum() <= 0:
        raise ValueError("Report area has no valid nonzero-length edges")
    fig = Figure(figsize=(12, 6), layout="constrained")
    FigureCanvasAgg(fig)
    axes = fig.subplots(1, 2)
    report = {
        "label": label,
        "edges": len(edges),
        "times": [],
        "tree_pct": float(
            np.average(model.edge_tree_frac[edges.eid], weights=lengths) * 100
        ),
    }
    for ax, hour, minute in zip(axes, (14, 18), (0, 30)):
        at = datetime.fromisoformat(date).replace(
            hour=hour, minute=minute, tzinfo=ZoneInfo("Europe/Warsaw")
        )
        shade = model.edge_shade(at)[edges.eid]
        position = model.sun(at)
        pct = float(np.average(shade, weights=lengths) * 100)
        edges.plot(ax=ax, column=shade, cmap="viridis_r", vmin=0, vmax=1, linewidth=1.5)
        ax.set_title(f"{at:%H:%M} — shade {pct:.1f}%")
        ax.set_axis_off()
        report["times"].append(
            {
                "at": at.isoformat(),
                "shade_pct": pct,
                "azimuth_deg": position.azimuth_deg,
                "elevation_deg": position.elevation_deg,
            }
        )
    fig.suptitle(f"{label} | {date} | trees {report['tree_pct']:.1f}%")
    fig.colorbar(
        axes[0].collections[0], ax=axes, label="Shade fraction (0–1)", shrink=0.7
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/processed/shade_comparison.png")
    )
    parser.add_argument("--date", default="2025-07-03")
    parser.add_argument(
        "--bbox", nargs=4, type=float, help="WGS84 west south east north"
    )
    parser.add_argument("--label", default="Prepared network")
    args = parser.parse_args()
    print(
        json.dumps(
            write_report(
                args.data_dir,
                args.output,
                date=args.date,
                bbox=args.bbox,
                label=args.label,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
