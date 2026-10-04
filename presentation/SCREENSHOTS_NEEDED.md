# BiKing — final presentation

`BiKing_HackYeah.pptx` contains the completed 10-slide jury deck in 16:9, with all three supplied screenshots embedded. Text, metric cards and diagrams remain editable in PowerPoint.

The generator reads screenshots from `presentation/` first and falls back to `presentation/assets/screenshots/`. Source PNGs are not modified; their aspect ratios are preserved. The main screen's browser toolbar is hidden with a native PowerPoint crop.

## Slide 3 — Main application screen

- Embedded source: `presentation/main_ui.png` (1866 × 1017 px).
- Visible: Kraków map, A/B waypoints, scenario, profile, departure controls and comfort/time slider. The browser toolbar is cropped in PowerPoint.

## Slide 7 — Fastest vs More comfortable

- Embedded source: `presentation/route_comparison.png` (1041 × 637 px).
- Visible: Both routes on the Kraków map with common A/B points. The legend matches the orange Fastest segments and blue More comfortable alternative. OpenStreetMap attribution is included below the map.

## Slide 8 — Route details and trade-off

- Embedded source: `presentation/route_detail.png` (370 × 782 px).
- Visible: Route cards, time/distance, shade, felt temperature, PM2.5 estimate, poor-air/high-UV minutes, avoided-street explanation and GPX controls. The portrait screenshot sits beside large editable trade-off highlights.

## Demo metrics — slides 7 and 8

Values are transcribed at the precision visible in the user-supplied `route_detail.png`. BiKing in slide 7's cards means More comfortable. The main screen on slide 3 shows a separate slider selection.

| Metric | Fastest | More comfortable |
| --- | ---: | ---: |
| Distance | 4.3 km | 5.5 km |
| Travel time | 17.3 min | 22.2 min |
| Shade | 12% | 47% |
| Felt temperature / UTCI model | 36.9°C | 34.8°C |
| PM2.5 dose / model estimate | 5.1 µg | 6.0 µg |
| High UV | 15.8 min | 10.8 min |
| Poor air | 2.9 min | 2.0 min |
| Discomfort | 9.0/10 | 8.1/10 |

The highlighted trade-off is +4.9 min (+28%), +35 percentage points of shade and −2.1°C felt temperature, with +18% modelled PM2.5 dose. The dose increase remains explicit. These are single-demo model outputs.

## View and regenerate

Open `BiKing_HackYeah.pptx` in PowerPoint and start the slideshow.
Regenerate from the repository root: `python presentation/generate_presentation.py`.
The generator requires all three PNGs and validates the saved PPTX archive, shape bounds and text layout. `validation.json` records the result.
`previews/contact_sheet.png` and `previews/slide_*.png` are static layout previews; they are not Office renders.
