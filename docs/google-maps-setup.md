# Google Maps setup

SensoryWay uses the Google Maps JavaScript API only for the interactive map background and map markers. Walking routes remain calculated by the backend through OpenRouteService, so the existing `ORS_API_KEY` remains separate and server-side.

## One-time Google Cloud setup

1. In Google Cloud Console, select or create a project and link a billing account.
2. Enable **Maps JavaScript API** for that project.
3. Create an API key and restrict it:
   - **Application restriction:** Websites.
   - **Allowed referrer for local development:** `http://localhost:3000/*`.
   - Add the production site address before deployment.
   - **API restriction:** Maps JavaScript API only.
4. Set a budget alert and a quota alert in Google Cloud Billing.

## Local configuration

Create `frontend/.env.local` (this file is ignored by Git) with the following values:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=your-restricted-browser-key
```

Restart `npm.cmd run dev` after saving the file, then open `http://localhost:3000`. The project fixes the development port to `3000`; if that port is occupied, stop the older frontend process with `Ctrl + C` before starting a new one.

`NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` is delivered to the browser by design. It is safe only when the key is restricted to the approved websites and to Maps JavaScript API. Never put the backend `ORS_API_KEY` in this file.

## Cost control

Google Maps Platform usage is billing-account based. Review the current free monthly usage caps and pricing in the Google Maps Platform documentation before a demo or production deployment. Use the project budget alert and API quota limit to prevent unexpected usage.
