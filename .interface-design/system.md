# Design System Contract — 音樂下載工具 (EasyMusicDL)

> Grounded in `.agents/skills/impeccable`, `.agents/skills/interface-design`, and `.agents/skills/elderly-ui-audit`.

## 1. Intent & Aesthetic Direction
- **Who**: High-age / senior Windows desktop users listening to Mandarin/Taiwanese classic songs at home.
- **What they must do**: Search a song by title or paste a YouTube link, download it as a pure MP3 to the Windows `Downloads` folder, and play or open it.
- **Feel**: **Native Windows 11 Fluent Utility** — calm, dignified, restrained, high-contrast, instantly legible without visual clutter. Zero decorative noise, zero emojis, zero competing rainbow buttons.

## 2. Color Tokens (Light / Dark)
All colors map to `src/ytdlp_gui/gui/theme.py`.

| Token | Light Mode | Dark Mode | Role |
| :--- | :--- | :--- | :--- |
| `bg_canvas` | `#F3F3F3` | `#202020` | Main window canvas & DWM titlebar caption |
| `bg_surface` | `#FFFFFF` | `#2B2B2B` | Toolbar, status bar, song rows, dialog panels |
| `bg_surface_subtle` | `#F8F8F8` | `#262626` | Secondary strips, table/status containers |
| `bg_input` | `#FAFAFA` | `#1C1C1C` | Inset text entry background |
| `bg_control` | `#FFFFFF` | `#323232` | Neutral secondary buttons |
| `bg_control_hover` | `#EFEFEF` | `#3C3C3C` | Hover state for neutral buttons |
| `border_hairline` | `#E2E2E2` | `#383838` | `1px` dividers and row outlines |
| `border_input` | `#C8C8C8` | `#4A4A4A` | Input & neutral button borders |
| `text_primary` | `#1A1A1A` | `#F3F3F3` | Headings, song titles, primary labels (WCAG AAA) |
| `text_secondary` | `#525252` | `#B8B8B8` | Channel, duration, helper text (WCAG AA+) |
| `accent` | `#0F6B4A` | `#2EA87A` | Primary CTA fill & active indicator (~10% screen area) |
| `accent_hover` | `#0B553B` | `#249168` | Primary CTA hover |
| `accent_subtle` | `#E6F4EE` | `#1B3B2F` | Active segmented control & clipboard banner surface |
| `accent_border` | `#9FD4BE` | `#2C6E56` | Subtle border on accent-tinted surfaces |
| `accent_text` | `#FFFFFF` | `#FFFFFF` | Text/icons on primary accent buttons |
| `danger` | `#B42318` | `#F87171` | Error text & error icon |
| `danger_bg` | `#FEF3F2` | `#381B1A` | Error banner background |
| `danger_border` | `#F5C2C0` | `#6E2B2A` | Error banner border |

## 3. Typography (`Microsoft JhengHei UI`)
- **Title / Splash Header**: `20px` Bold
- **Song Title / Primary Row Heading**: `18px` Bold
- **Primary Button / Nav Tab / Search Input**: `16px` Bold (Input `16px` Regular)
- **Secondary Button / Body**: `15px` Bold/Regular
- **Metadata (Channel, Duration, File Size, Date)**: `14px` Regular
- **Status Bar**: `13px` Regular

## 4. Spacing, Radii & Hit Targets
- **Base grid**: `4px` / `8px` multiples (`8`, `12`, `16`, `20`, `24`).
- **Corner radii**: `6px` on buttons, inputs, segmented controls; `8px` on rows, panels, and dialogs.
- **Border width**: Strictly `1px` (hairline) or `0px` (never `2px` heavy borders).
- **Hit targets**: Primary search & download actions `46–50px` height; toolbar/secondary controls `40–44px` height (exceeding 44px accessibility floor for primary tasks).

## 5. Iconography & Microcopy
- **Zero emojis**: All icons rendered from Windows `Segoe Fluent Icons` (`SegoeIcons.ttf` / `segmdl2.ttf`) at 2× resolution via Pillow into monochrome `CTkImage`.
- **Voice**: Direct, respectful verb+object Traditional Chinese (`搜尋`, `貼上網址`, `下載 MP3`, `播放`, `開啟資料夾`, `設定與修復`). No exclamation spam or cutesy particles.
