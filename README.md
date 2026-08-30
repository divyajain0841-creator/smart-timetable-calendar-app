# TimetableFlow v2

## What you asked for → what this build does

1. **Upload a timetable screenshot/PDF** → accepts PNG/JPG/JPEG/PDF.
2. **No data-type conversion** → users upload the original timetable file; the backend handles image/PDF processing.
3. **Detect the table grid** → OpenCV estimates the metadata/session geometry instead of depending only on OCR labels.
4. **Identify merged cells** → OCR coordinates are combined with horizontal cell spans so a class covering multiple sessions can become one calendar event.
5. **Identify session boundaries** → seven main session columns and a four-session Saturday layout are supported, with OCR time labels used when they are clear and sensible defaults otherwise.
6. **Map Course Name + Code + Teacher + Classroom + Type** → the parser uses the physical row position plus OCR text; users can remove/re-add entries before export.
7. **Weekly application** → semester start/end control the generated weekly occurrences.
8. **Optional holidays/exceptions** → exception mode is optional; one-off holidays and 2nd/3rd/4th Saturday rules are available.
9. **Academic calendar upload** → an academic calendar image/PDF can be OCR'd for dates; detected dates are added for review.
10. **Choose a calendar** → Google Calendar direct API is supported when OAuth is configured; Apple/Samsung/Android/system calendars use `.ics`, the standard cross-platform calendar format.
11. **Permanent timetable changes** → upload a replacement timetable, compare added/removed/changed classes, set an effective date, then make the replacement active. The UI is review-first to avoid silent duplicate events.
12. **The Android `content://` OCR failure** → OCR is server-side. The browser no longer needs a Tesseract Web Worker, eliminating the specific failure shown in the screenshots.
13. **Eye-catching opening page** → dark premium hero, glass calendar mockup, gradient accents, four-step workflow, rounded cards, mobile responsive layout.

## Design overview

The opening screen is designed to feel like a modern productivity SaaS rather than a college utility:

- **Deep navy gradient hero** with cyan/purple light effects creates immediate visual hierarchy.
- **TimetableFlow** wordmark makes the product feel like a finished service.
- The headline communicates the value proposition immediately: **"Your timetable, finally where it belongs."**
- A glass-style calendar illustration visually explains the product before the user uploads anything.
- The four-step strip makes the workflow obvious: Upload → Detect → Review → Export.
- White cards on a very light background keep the dense settings readable.
- Buttons and status messages use strong visual states for processing, success and errors.
- The layout collapses cleanly on phones.

## Correct deployment model

Do **not** open `frontend/index.html` directly from Downloads. That recreates the local-file environment that caused the previous OCR error.

The intended flow is:

```text
Phone/PC browser
      ↓ HTTPS
TimetableFlow web server
      ↓
FastAPI backend
      ↓
OpenCV + Tesseract
      ↓
Structured timetable
      ↓
Review
      ↓
Google Calendar OR .ics
```

## Run locally with Docker

From the project root:

```bash
docker compose up --build
```

Open:

```text
http://localhost:8000
```

## GitHub + Render deployment

1. Create an empty GitHub repository.
2. Upload the **contents** of this project so `Dockerfile` is at repository root.
3. On Render create a **Web Service** from that GitHub repository.
4. Select the Docker runtime.
5. Deploy.
6. Open the HTTPS URL Render gives you.

## Google Calendar

Google Calendar needs OAuth credentials owned by the site operator. Set:

```text
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://YOUR-DOMAIN/api/google/callback
SESSION_SECRET=long-random-value
COOKIE_SECURE=true
```

The Google OAuth consent screen must allow the Calendar scope used by the application.

## Apple / Samsung / Android / System calendar

The web cannot universally write directly into every device's private calendar database. The correct interoperable method is to generate a standard `.ics` file. Users open/import that file with Apple Calendar, Samsung Calendar, Google Calendar or their system calendar app.

## Production upgrade for permanent changes

The current build deliberately compares and reviews replacement timetables before export. For a fully automatic Google synchronization service, add a database storing the provider event IDs and timetable version/effective date. Then a replacement can update/delete only future events from the effective date and preserve historical events.

## OCR expectations

OCR is probabilistic. The application therefore never treats OCR output as final truth. It exposes the detected classes for review. For the supplied BBA-style timetable, the parser is built around its actual characteristics: dense five-row course metadata, seven main sessions, a separate Saturday table, colored/merged cells and faint grid lines.
