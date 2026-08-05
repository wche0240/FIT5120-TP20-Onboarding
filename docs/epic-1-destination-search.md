# Epic 1 Melbourne CBD Location Search

## Purpose

The onboarding MVP lets a user enter a Melbourne CBD address, street or landmark as either a start point or destination. Suggested locations remain available for fast demonstration, but a user is no longer limited to that list.

## Flow

1. The user enters an address, street or landmark in the start or destination field.
2. The user explicitly selects that field's search icon or presses Enter. The frontend then sends one location-search request and shows the returned candidates.
3. The user selects a candidate, then chooses `Find routes`.
4. The backend applies an Australian country filter and a bounded Melbourne CBD viewbox.
5. It independently verifies that every returned coordinate is within the MVP CBD boundary before returning it to the frontend.
6. The route API performs the same boundary validation before requesting walking routes.

## Geocoding service and privacy

The default provider is [Nominatim Search](https://nominatim.org/release-docs/latest/api/Search/), configured through `GEOCODER_SEARCH_URL`. The public Nominatim service is suitable only for this low-volume, user-triggered educational demonstration. The implementation follows the published [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/): it does not use type-ahead autocomplete, sends an identifying User-Agent, caches up to 100 distinct queries, and rate-limits uncached requests to one per second.

Search terms are sent to the configured geocoder. Users should not enter private home addresses, personal information, or sensitive location details. The provider can be replaced in `.env` without changing frontend code.

## Acceptance evidence

Demonstrate a route from `Melbourne Central` to `State Library Victoria` entered as text. Search each field explicitly, select the returned candidate, then select `Find routes`. The result should show the resolved locations, walking route options, crowd-data status, and nearby public-transport access points.
