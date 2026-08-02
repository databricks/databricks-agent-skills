# Theme & Color

The dashboard theme block and colour rules. Read this when creating a new
dashboard or when a review flags colour, contrast, or palette.

### Theme & Color (always set this — it makes or breaks the dashboard)

Top-level `uiSettings.theme` controls colors, fonts, and widget chrome across every widget on the dashboard. Without it, the dashboard inherits the workspace default and looks generic. **Set the full block on every dashboard you create** — a coherent palette is the single highest-impact polish item.

Mental model — **60/30/10 rule** mapped to theme keys: **60% neutral** = canvas/widget/border backgrounds (set `widgetBorderColor = widgetBackgroundColor` to hide borders); **30% secondary** = `fontColor` + `visualizationColors` (the content weight); **10% accent** = `selectionColor` for filters / tabs / active selections — pick something distinct from text and palette; a safe-blue around `#2272B4` matches the hyperlink convention and works as a default.

```json
{
  "datasets": [...],
  "pages": [...],
  "uiSettings": {
    "theme": {
      "canvasBackgroundColor": {"light": "#FCFCFC", "dark": "#1F272D"},
      "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#11171C"},
      "fontColor":             {"light": "#11171C", "dark": "#E8ECF0"},
      "selectionColor":        {"light": "#2272B4", "dark": "#8ACAFF"},
      "visualizationColors": [
        "#FFA600", "#FF7054", "#DE5582", "#995495",
        "#4E5185", "#1D425C", "#99DDB4"
      ],
      "widgetHeaderAlignment": "LEFT"
    }
  }
}
```

**Theme keys** (mechanics):

- `visualizationColors`: ordered palette every chart series and category mapping cycles through. **Positions are 0-indexed**: `position: 0` = first color (`#FFA600` above), `position: 6` = seventh (`#99DDB4`). Length 5–8 is typical.
- Background / font / selection colors take `light` + `dark` pairs; the dashboard auto-selects based on viewer mode.
- `widgetHeaderAlignment`: `"LEFT"` (default), `"CENTER"`, or `"RIGHT"`. Optional top-level: `fontFamily` (e.g. `"Space Grotesk"`, `"Inter"` — sans-serif keeps dense data readable; don't override per widget) and `widgetCornerRadius` (integer px, e.g. `12` for rounded corners; `0` or omit = square).
- Per-widget color references: `{"themeColorType": "visualizationColors", "position": N}` (0-indexed) to pin to a palette slot, or `{"hex": "#FF0000"}` for an exact color outside the palette.

**Palette-design rules** (this is what separates a polished dashboard from a noisy one):

1. **One coherent color family per dashboard, distinct across the suite.** Walk **across hues** (e.g., amber → coral → pink → purple → navy), not one color faded toward white — a single-hue lightness ramp reads as one color and the viewer can't tell categories apart. Adjacent stops must be visually distinct: if you squint and two blur into one, push them further apart. Single-hue ramps are for **quantitative** widgets only (`colorRamp.mode: "custom-sequential"`), never for `visualizationColors`.
2. **Pin semantic colors as literal hex, outside the palette.** "Bad" = a warm coral (e.g. `#FF7E5C`), "good" = a calm teal/green. Use `color.scale.mappings` with a bare hex string — `{"value": "Critical", "color": "#FF7E5C"}` — **not** `{"hex": "..."}` or `themeColorType: position` (both are silently dropped on chart widgets). Reuse the good-teal that's already in the palette so it never clashes.
3. **Color non-categorical widgets explicitly so they join the family.** Maps & heatmaps: `colorRamp.mode: "custom-sequential"` with `{start, end}` from the family (if directional: `start` = bad color, `end` = good color). Forecast / multi-series: pin per-series via `color.scale.mappings` keyed on `displayName` (actual = solid family color, forecast = contrast/alert, threshold = muted tone). Sparkline counters: set `value.color` to a family color, not grey.
4. **"Lighter / more pastel" tweak**: nudge all stops up in lightness *together*; don't recolor individual ones. Re-sync the pinned semantic hex values; keep enough contrast on the alert color that it still reads as a warning.

**Starter palettes** (pick one and adapt — extend to 7-8 stops if needed; semantic red/green stay as literal hex per rule 2):

```
#094074  #3C6997  #5ADBFF  #FFDD4A  #FE9000
#003F5C  #594E90  #BC4C96  #FF5F66  #FFA600
#4A8CC7  #F59770  #FFD84A  #F0E09E  #6DD980
#440154  #3B528B  #21918C  #5EC962  #FDE725
#4E79A7  #F28E2C  #E15759  #76B7B2  #59A14F
#0072B2  #E69F00  #009E73  #CC79A7  #D55E00
#0D0887  #7E03A8  #CC4778  #F89441  #F0F921
#6929C4  #1192E8  #005D5D  #9F1853  #FA4D56
```

~4-5% of viewers have color blindness (mostly red/green). Rows 4 and 6 above (viridis, Okabe-Ito) are CB-safe by design; verify customized palettes via simulator (Adobe Color, `colorbrewer2.org`). Don't put red and green adjacent, and rely on lightness contrast — not hue alone — between adjacent stops.
