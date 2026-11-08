---
name: Refinery
description: AI change attestation for enterprise COBOL
colors:
  ground: "#09090B"
  surface: "#18181B"
  surface-2: "#1F1F23"
  border: "#27272A"
  ink: "#F4F4F5"
  muted: "#A1A1AA"
  tertiary: "#71717A"
  green: "#00D46A"
  error: "#EF4444"
typography:
  hero:
    fontFamily: "Work Sans, sans-serif"
    fontSize: "60px"
    fontWeight: 400
    lineHeight: 0.97
    letterSpacing: "-0.04em"
  cta-heading:
    fontFamily: "Work Sans, sans-serif"
    fontSize: "56px"
    fontWeight: 400
    lineHeight: 1.05
    letterSpacing: "-0.03em"
  section-heading:
    fontFamily: "Work Sans, sans-serif"
    fontSize: "40px"
    fontWeight: 400
    lineHeight: 1.1
    letterSpacing: "-0.025em"
  minor-heading:
    fontFamily: "Work Sans, sans-serif"
    fontSize: "32px"
    fontWeight: 400
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  card-title:
    fontFamily: "Work Sans, sans-serif"
    fontSize: "22px"
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  subhead:
    fontFamily: "Inter, sans-serif"
    fontSize: "20px"
    fontWeight: 400
    lineHeight: 1.5
  body:
    fontFamily: "Inter, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  card-body:
    fontFamily: "Inter, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  nav-link:
    fontFamily: "Inter, sans-serif"
    fontSize: "15px"
    fontWeight: 500
  button:
    fontFamily: "Inter, sans-serif"
    fontSize: "14px"
    fontWeight: 600
  legal:
    fontFamily: "Inter, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  badge: "4px"
  button: "6px"
  card: "8px"
  competitor: "10px"
  panel: "12px"
  pill: "100px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
  "10": "40px"
  "12": "48px"
  "14": "56px"
  "16": "64px"
  "20": "80px"
  "30": "120px"
components:
  button-primary:
    backgroundColor: "{colors.green}"
    textColor: "{colors.ground}"
    typography: "{typography.button}"
    rounded: "{rounded.button}"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "32px"
---

# Design System: Refinery

A fixture for the `designing-products` tokens generator and detector check, in the format of
Impeccable's `document` (token frontmatter, canonical sections). Values from the refinery-design
skill, sections 1 to 4.

## Overview

Dark, flat, one accent. Green means verified.

## Colors

### Primary

- **Green** (`#00D46A`): the single accent and every verdict. On dark grounds only.

### Neutral

- **Ground** (`#09090B`), **Surface** (`#18181B`), **Surface 2** (`#1F1F23`): page, cards, competitor cards.
- **Border** (`#27272A`): every border, 1px.
- **Ink** (`#F4F4F5`), **Muted** (`#A1A1AA`), **Tertiary** (`#71717A`): headings, body, meta.
- **Error** (`#EF4444`): defect alerts only.

## Typography

Work Sans 400 for every heading; Inter for body and UI. Contrast from size and colour, not weight.

## Shapes

Badges 4px, buttons 6px, cards 8px, competitor cards 10px, large panels 12px, the pill full.
