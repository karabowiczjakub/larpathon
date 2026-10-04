# BiKing — final screenshots

The finished presentation already exists at `BiKing_HackYeah.pptx`. Missing images have designed placeholders; all slide diagrams are editable.

Put final screenshots in `presentation/assets/screenshots/`. The generator automatically contains each image in its existing frame without cropping. Existing screenshots are not modified.

## Capture readiness

This checkout contains the implemented Flask/Leaflet app, environmental scenarios, fuzzy tables and a synthetic shade preview. It currently lacks the city-wide `graph.npz`, `edges.parquet`, `edge_coords.npz`, `shade.npy`, `shade_bins.json` and `edge_tree_frac.npy` in `data/processed/`. Load matching artifacts before capturing real Kraków routing. The optional `edge_heat.npz` is also absent.

Check `/api/health` before capture. A mock fallback must not be presented as real city data. Historical scenario data is legitimate when the selected scenario and departure time remain visible. Do not replace missing screenshots with generated UI or hand-drawn routes.

## Slide 3 — main_ui.png

- Status: Missing — placeholder.
- Visible: Kraków map, A/B waypoints, scenario, profile and departure controls.
- Recommended application state: Use the real Flask/Leaflet app in light mode at a desktop viewport. Select the heatwave scenario and a profile; keep the map and controls unobstructed. Choose origin and destination, then let route calculation finish.
- Must not be visible: Loading overlay, browser chrome, devtools, errors, unrelated tabs, mock data passed off as city data, open accessibility popovers.
- Why it matters: Shows that the user journey lives in one working application screen.
- Recommended size: 1600 × 950 or a similar landscape aspect ratio; capture the application only.

## Slide 7 — route_comparison.png

- Status: Missing — placeholder.
- Visible: Both routes on one map, identical origin/destination, dashed grey Fastest and solid green More comfortable, route legend and visible route separation.
- Recommended application state: First load matching city graph and shade artifacts. Verify /api/health reports real graph, shade, environment and exposure modules. Use Heatwave · 3 Jul 2025, 14:00 and Senior / Child as a starting point. The existing Load demo route preset uses Kazimierz → Rondo Mogilskie → Nowa Huta. Check that the returned routes actually differ; otherwise choose another real A/B pair. Keep all factors enabled. Capture the map and save the /api/route response from that same run for metric entry.
- Must not be visible: Different endpoints or times for the two routes, synthetic fixture networks, a mock result labelled real, manual route drawings, invented gains, loading states. Retain OpenStreetMap attribution when map tiles are visible.
- Why it matters: Demonstrates that environmental edge costs can change the route geometry.
- Recommended size: 1900 × 850 or a similar wide map crop; leave enough detail to see both routes.

## Slide 8 — route_details.png

- Status: Missing — placeholder.
- Visible: Real route cards, time/distance, shade, felt temperature, PM2.5 estimate, poor-air/high-UV minutes, actual avoided-street explanation, comfort/time slider and GPX export control. Keep some map visible if practical.
- Recommended application state: Use the same fully calculated route request as slide 7, preferably with more than one valid trade-off option. Select More comfortable, scroll only enough to show its card and the trade-off panel. If the UI reports no useful detour, show that honest state or select a different real demo pair.
- Must not be visible: Mock numbers, fabricated explanation text, clipped cards, open tooltips obscuring metrics, health claims beyond the model, debug panes and loading overlays.
- Why it matters: Shows how GIS and environmental modelling become an understandable choice.
- Recommended size: 1500 × 850 or a similar landscape crop. Preserve text legibility.

## Slide 7 metric cards

All current values are `—`. After capturing the final comparison, use the exact same `/api/route` response to enter both routes' `time_min`, `shade_pct`, `utci_avg_c` and `pm25_dose_ug` in the editable cards. BiKing in these cards means More comfortable. Preserve the model labels for UTCI and PM2.5 dose. Screenshot replacement does not invent or infer metric values.

## Shadow screenshot

No `shadow_debug.png` is required. Slide 6 is complete with a native PowerPoint geometry diagram and the actual ray-marching inequality. The existing `data/shade_preview/shade_comparison.png` is synthetic and is deliberately not used as a real-city screenshot.
