# ADR 0005: Icons ausschließlich als SVG

- **Status:** accepted
- **Datum:** 2026-04-23

## Kontext
Die Chrome-Extension zeigt Status-Badges (Favorit gesetzt, Download-Status pro
Staffel/Episode) auf stark unterschiedlichen Hintergründen. Das Design muss in
hell und dunkel funktionieren und in Retina-/4K-Displays scharf bleiben.
Außerdem will ich Icons im Code diffbar haben.

## Entscheidung
**Alle Icons sind SVGs.** Keine PNG/JPG-Icons in UI-Elementen.

Ausnahmen, die **keine Icons** sind:
- Cover-Artwork (Poster, Backdrops) bleibt JPG/PNG — das ist Content, kein Icon.
- Chrome-Manifest verlangt PNG-Varianten (`16/48/128 px`) → die werden aus einem
  Master-SVG via `make icons` generiert, nicht von Hand gepflegt.

## Alternativen
- **Icon-Fonts (Font Awesome etc.):** größer, CSS-pseudo-element-Akrobatik,
  Accessibility-Probleme.
- **PNG pro Icon:** blurry auf Retina, keine `currentColor`, größerer Bundle,
  Diff-unfreundlich.

## Konsequenzen
- `extension/icons/svg/` ist die Quelle der Wahrheit.
- Icons werden im Content-Script inline per `fetch` geladen → `currentColor`
  funktioniert, ein Stylesheet-Wechsel ändert die Icon-Farbe ohne neues Asset.
- Bei neuen Icons: SVG zeichnen/exportieren (kein PNG committen), klare
  stroke-/fill-Semantik prüfen.
