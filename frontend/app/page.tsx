"use client";

import dynamic from "next/dynamic";
import {
  AlertTriangle,
  Bookmark,
  BookmarkCheck,
  BookmarkPlus,
  Compass,
  LoaderCircle,
  MapPinned,
  Menu,
  Navigation,
  Route,
  Search,
  TrainFront,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import type { MapPoint, MapRoute, TransitAccessPoint } from "@/components/SensoryWayMap";

const SensoryWayMap = dynamic(() => import("@/components/SensoryWayMap"), {
  ssr: false,
  loading: () => <div className="map-loading">Loading map...</div>,
});

type CrowdLevel = "low" | "medium" | "high";

type Place = MapPoint & {
  label: string;
  detail: string;
};

type ApiRoute = MapRoute & {
  distance_metres: number;
  duration_seconds: number;
  data_status: "available" | "stale" | "unavailable";
  crowd_score: number | null;
  data_coverage_confidence: number | null;
  matched_sensor_count: number;
  meets_crowd_threshold: boolean | null;
  warning: string | null;
};

type RoutesResponse = {
  status: "available" | "degraded";
  requested_max_crowd_level: CrowdLevel;
  recommended_route_id: number | null;
  routes: ApiRoute[];
  warning: string | null;
};

type LocationSearchResult = {
  name: string;
  display_name: string;
  longitude: number;
  latitude: number;
};

type SearchField = "start" | "destination";

type AppView = "explore" | "saved";

type SavedRoute = {
  id: string;
  startLabel: string;
  destinationLabel: string;
  crowdLevel: CrowdLevel;
  distanceMetres: number;
  durationSeconds: number;
};

const SAVED_ROUTES_STORAGE_KEY = "sensoryway-saved-routes";

const PLACES: Place[] = [
  { label: "Melbourne Central", detail: "La Trobe Street, Melbourne", latitude: -37.81, longitude: 144.9631 },
  { label: "Flinders Street Station", detail: "Flinders Street, Melbourne", latitude: -37.8183, longitude: 144.9667 },
  { label: "State Library Victoria", detail: "Swanston Street, Melbourne", latitude: -37.8109, longitude: 144.9645 },
  { label: "Flagstaff Gardens", detail: "William Street, Melbourne", latitude: -37.8105, longitude: 144.9555 },
  { label: "Collins Street destination", detail: "Collins Street, Melbourne", latitude: -37.814, longitude: 144.975 },
];

const CROWD_OPTIONS: { value: CrowdLevel; label: string; help: string }[] = [
  { value: "low", label: "Low", help: "Only quieter routes" },
  { value: "medium", label: "Medium", help: "Avoid high crowd levels" },
  { value: "high", label: "High", help: "Show every monitored route" },
];

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function findPlace(label: string) {
  return PLACES.find((place) => place.label.toLowerCase() === label.trim().toLowerCase());
}

function placeFromSearchResult(location: LocationSearchResult): Place {
  return {
    label: location.name,
    detail: location.display_name,
    longitude: location.longitude,
    latitude: location.latitude,
  };
}

function formatDistance(metres: number) {
  return metres >= 1000 ? `${(metres / 1000).toFixed(1)} km` : `${Math.round(metres)} m`;
}

function formatDuration(seconds: number) {
  return `${Math.max(1, Math.round(seconds / 60))} min`;
}

function routeLabel(route: ApiRoute) {
  if (route.crowd_level === "low") return "Least crowded";
  if (route.crowd_level === "medium") return "Moderate crowd";
  if (route.crowd_level === "high") return "Very crowded";
  return "Crowd data unavailable";
}

function confidenceLabel(route: ApiRoute) {
  if (route.data_coverage_confidence === null || route.data_coverage_confidence === undefined) {
    return "Coverage N/A";
  }
  return `Coverage ${route.data_coverage_confidence.toFixed(1)}%`;
}

function confidenceTone(route: ApiRoute) {
  if (route.data_status !== "available" || route.data_coverage_confidence === null || route.data_coverage_confidence === undefined) {
    return "unknown";
  }
  if (route.data_coverage_confidence >= 70) return "high";
  if (route.data_coverage_confidence >= 40) return "medium";
  return "low";
}

export default function HomePage() {
  const [startLabel, setStartLabel] = useState("Melbourne Central");
  const [destinationLabel, setDestinationLabel] = useState("Collins Street destination");
  const [resolvedStart, setResolvedStart] = useState<Place | null>(PLACES[0]);
  const [resolvedDestination, setResolvedDestination] = useState<Place | null>(PLACES[4]);
  const [locationSearchField, setLocationSearchField] = useState<SearchField | null>(null);
  const [locationSuggestions, setLocationSuggestions] = useState<LocationSearchResult[]>([]);
  const [locationSearchError, setLocationSearchError] = useState<string | null>(null);
  const [isSearchingLocations, setIsSearchingLocations] = useState(false);
  const [crowdLevel, setCrowdLevel] = useState<CrowdLevel>("medium");
  const [result, setResult] = useState<RoutesResponse | null>(null);
  const [activeRouteId, setActiveRouteId] = useState<number | null>(null);
  const [goRouteId, setGoRouteId] = useState<number | null>(null);
  const [transitAccessPoints, setTransitAccessPoints] = useState<TransitAccessPoint[]>([]);
  const [nearbyTransit, setNearbyTransit] = useState<{ start: TransitAccessPoint[]; destination: TransitAccessPoint[] }>({ start: [], destination: [] });
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [activeView, setActiveView] = useState<AppView>("explore");
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [savedRoutes, setSavedRoutes] = useState<SavedRoute[]>([]);
  const [savedRoutesLoaded, setSavedRoutesLoaded] = useState(false);

  const start = resolvedStart ?? findPlace(startLabel) ?? PLACES[0];
  const destination = resolvedDestination ?? findPlace(destinationLabel) ?? PLACES[4];
  const visibleRoutes = useMemo(() => {
    if (!result) return [];
    if (goRouteId === null) return result.routes;
    return result.routes.filter((route) => route.route_id === goRouteId);
  }, [goRouteId, result]);

  const activeRoute = useMemo(() => {
    if (visibleRoutes.length === 0) return null;
    return visibleRoutes.find((route) => route.route_id === activeRouteId) ?? visibleRoutes[0] ?? null;
  }, [activeRouteId, visibleRoutes]);

  useEffect(() => {
    let isCurrent = true;

    async function loadTransitAccessPoints() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/transit-access-points?limit=800`);
        const body = (await response.json()) as TransitAccessPoint[];
        if (response.ok && isCurrent) setTransitAccessPoints(body);
      } catch {
        // Route planning remains usable when the optional map layer cannot load.
      }
    }

    void loadTransitAccessPoints();
    return () => { isCurrent = false; };
  }, []);

  useEffect(() => {
    try {
      const storedRoutes = window.localStorage.getItem(SAVED_ROUTES_STORAGE_KEY);
      if (storedRoutes) setSavedRoutes(JSON.parse(storedRoutes) as SavedRoute[]);
    } catch {
      setSavedRoutes([]);
    } finally {
      setSavedRoutesLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (savedRoutesLoaded) window.localStorage.setItem(SAVED_ROUTES_STORAGE_KEY, JSON.stringify(savedRoutes));
  }, [savedRoutes, savedRoutesLoaded]);

  async function loadNearbyTransit(selectedStart: Place, selectedDestination: Place) {
    const accessPointRequest = async (place: Place) => {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/transit-access-points?longitude=${place.longitude}&latitude=${place.latitude}&radius_metres=500&limit=2`
      );
      if (!response.ok) return [];
      return (await response.json()) as TransitAccessPoint[];
    };

    try {
      const [startPoints, destinationPoints] = await Promise.all([accessPointRequest(selectedStart), accessPointRequest(selectedDestination)]);
      setNearbyTransit({ start: startPoints, destination: destinationPoints });
    } catch {
      setNearbyTransit({ start: [], destination: [] });
    }
  }

  async function searchLocations(query: string) {
    if (query.trim().length < 3) {
      throw new Error("Enter at least three characters to search for an address.");
    }

    const response = await fetch(`${API_BASE_URL}/api/v1/location-search?query=${encodeURIComponent(query.trim())}`);
    const body = (await response.json()) as LocationSearchResult[] | { detail?: string };
    if (!response.ok || !Array.isArray(body)) {
      throw new Error("detail" in body ? body.detail ?? "Could not search for that address." : "Could not search for that address.");
    }
    return body;
  }

  async function resolvePlace(label: string, resolvedPlace: Place | null, field: SearchField) {
    const suggestedPlace = findPlace(label);
    if (suggestedPlace) return suggestedPlace;
    if (resolvedPlace) return resolvedPlace;

    const matches = await searchLocations(label);
    const selectedLocation = matches[0];
    if (!selectedLocation) {
      throw new Error(`No matching ${field} was found inside the Melbourne CBD.`);
    }
    return placeFromSearchResult(selectedLocation);
  }

  async function searchAddress(field: SearchField) {
    const query = field === "start" ? startLabel : destinationLabel;
    setLocationSearchField(field);
    setLocationSearchError(null);
    setLocationSuggestions([]);
    setIsSearchingLocations(true);

    try {
      const matches = await searchLocations(query);
      setLocationSuggestions(matches);
      if (matches.length === 0) {
        setLocationSearchError("No matching address was found inside the Melbourne CBD.");
      }
    } catch (searchError) {
      setLocationSearchError(searchError instanceof Error ? searchError.message : "Could not search for that address.");
    } finally {
      setIsSearchingLocations(false);
    }
  }

  function selectAddress(field: SearchField, location: LocationSearchResult) {
    const place = placeFromSearchResult(location);
    if (field === "start") {
      setStartLabel(place.label);
      setResolvedStart(place);
    } else {
      setDestinationLabel(place.label);
      setResolvedDestination(place);
    }
    setLocationSearchField(null);
    setLocationSuggestions([]);
    setLocationSearchError(null);
  }

  function selectTransitPoint(field: SearchField, accessPoint: TransitAccessPoint) {
    const place: Place = {
      label: accessPoint.name,
      detail: `${accessPoint.mode} stop`,
      longitude: accessPoint.longitude,
      latitude: accessPoint.latitude,
    };

    if (field === "start") {
      setStartLabel(place.label);
      setResolvedStart(place);
    } else {
      setDestinationLabel(place.label);
      setResolvedDestination(place);
    }
    setLocationSearchField(null);
    setLocationSuggestions([]);
    setLocationSearchError(null);
    setError(null);
    setResult(null);
    setActiveRouteId(null);
    setNearbyTransit({ start: [], destination: [] });
  }

  async function planRoute(event?: FormEvent) {
    event?.preventDefault();

    setIsLoading(true);
    setError(null);
    try {
      const [selectedStart, selectedDestination] = await Promise.all([
        resolvePlace(startLabel, resolvedStart, "start"),
        resolvePlace(destinationLabel, resolvedDestination, "destination"),
      ]);
      setResolvedStart(selectedStart);
      setResolvedDestination(selectedDestination);
      const response = await fetch(`${API_BASE_URL}/api/v1/routes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start: { longitude: selectedStart.longitude, latitude: selectedStart.latitude },
          destination: { longitude: selectedDestination.longitude, latitude: selectedDestination.latitude },
          max_crowd_level: crowdLevel,
        }),
      });
      const body = (await response.json()) as RoutesResponse | { detail?: string };
      if (!response.ok || !("routes" in body)) {
        throw new Error("detail" in body ? body.detail ?? "Could not plan a route." : "Could not plan a route.");
      }
      setResult(body);
      setActiveRouteId(body.recommended_route_id ?? body.routes[0]?.route_id ?? null);
      setGoRouteId(null);
      void loadNearbyTransit(selectedStart, selectedDestination);
    } catch (requestError) {
      setResult(null);
      setActiveRouteId(null);
      setGoRouteId(null);
      setError(requestError instanceof Error ? requestError.message : "Could not plan a route.");
    } finally {
      setIsLoading(false);
    }
  }

  function selectRouteAndGo(routeId: number) {
    setActiveRouteId(routeId);
    setGoRouteId(routeId);
  }

  function showAllRoutes() {
    setGoRouteId(null);
    if (result?.recommended_route_id) {
      setActiveRouteId(result.recommended_route_id);
    }
  }

  function selectView(view: AppView) {
    setActiveView(view);
    setIsDrawerOpen(false);
  }

  const activeSavedRouteId = activeRoute ? `${startLabel}:${destination.label}:${crowdLevel}:${activeRoute.route_id}` : null;
  const activeRouteIsSaved = activeSavedRouteId ? savedRoutes.some((route) => route.id === activeSavedRouteId) : false;

  function saveActiveRoute() {
    if (!activeRoute || !activeSavedRouteId) return;
    const routeToSave: SavedRoute = {
      id: activeSavedRouteId,
      startLabel,
      destinationLabel: destination.label,
      crowdLevel,
      distanceMetres: activeRoute.distance_metres,
      durationSeconds: activeRoute.duration_seconds,
    };
    setSavedRoutes((routes) => routes.some((route) => route.id === routeToSave.id) ? routes : [routeToSave, ...routes]);
  }

  function restoreSavedRoute(savedRoute: SavedRoute) {
    setStartLabel(savedRoute.startLabel);
    setDestinationLabel(savedRoute.destinationLabel);
    setResolvedStart(findPlace(savedRoute.startLabel) ?? null);
    setResolvedDestination(findPlace(savedRoute.destinationLabel) ?? null);
    setCrowdLevel(savedRoute.crowdLevel);
    selectView("explore");
  }

  return (
    <main className="app-shell">
      <nav className="desktop-rail" aria-label="Primary navigation">
        <button className="icon-button rail-menu" type="button" aria-label="Open navigation" title="Open navigation" onClick={() => setIsDrawerOpen(true)}><Menu size={21} /></button>
        <div className="rail-links">
          <button className={activeView === "explore" ? "rail-link is-active" : "rail-link"} type="button" aria-label="Explore routes" title="Explore routes" onClick={() => selectView("explore")}><Compass size={21} /><span>Explore</span></button>
          <button className={activeView === "saved" ? "rail-link is-active" : "rail-link"} type="button" aria-label="Saved routes" title="Saved routes" onClick={() => selectView("saved")}><Bookmark size={20} /><span>Saved</span></button>
        </div>
      </nav>

      <section className="map-stage" aria-label="Route planner">
        <SensoryWayMap start={start} destination={destination} routes={visibleRoutes} transitAccessPoints={transitAccessPoints} crowdDataAvailable={result?.status === "available"} activeRouteId={activeRouteId} onRouteSelect={setActiveRouteId} onTransitPointSelect={selectTransitPoint} />

        <aside className="map-sidebar" aria-label="SensoryWay workspace">
          {activeView === "explore" ? <>
          <header className="planner-header">
          <div className="brand-mark" aria-hidden="true"><Navigation size={19} fill="currentColor" /></div>
          <div className="brand-copy"><strong>SensoryWay</strong><span>Melbourne CBD</span></div>
          </header>

          <form className="directions-form" onSubmit={planRoute}>
            <h1>Plan a walk</h1>
            <div className="direction-fields">
              <div className="place-field">
                <MapPinned size={18} aria-hidden="true" />
                <label htmlFor="start-place">Start</label>
                <input id="start-place" value={startLabel} autoComplete="off" onChange={(event) => { setStartLabel(event.target.value); setResolvedStart(null); setLocationSearchField(null); setLocationSuggestions([]); setLocationSearchError(null); }} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void searchAddress("start"); } }} placeholder="Enter a CBD address or landmark" />
                <button className="address-search-button" type="button" aria-label="Search start address" title="Search start address" onClick={() => void searchAddress("start")} disabled={isSearchingLocations}>
                  {isSearchingLocations && locationSearchField === "start" ? <LoaderCircle className="spin" size={18} /> : <Search size={18} />}
                </button>
              </div>
              {locationSearchField === "start" ? <div className="address-results" role="listbox" aria-label="Start address results">
                {isSearchingLocations ? <p>Searching addresses...</p> : null}
                {!isSearchingLocations && locationSearchError ? <p>{locationSearchError}</p> : null}
                {!isSearchingLocations && !locationSearchError ? locationSuggestions.map((location) => <button key={`${location.longitude}:${location.latitude}`} type="button" role="option" onClick={() => selectAddress("start", location)}><MapPinned size={17} /><span><strong>{location.name}</strong><small>{location.display_name}</small></span></button>) : null}
              </div> : null}
              <div className="place-field">
                <Search size={18} aria-hidden="true" />
                <label htmlFor="destination-place">Destination</label>
                <input id="destination-place" value={destinationLabel} autoComplete="off" onChange={(event) => { setDestinationLabel(event.target.value); setResolvedDestination(null); setLocationSearchField(null); setLocationSuggestions([]); setLocationSearchError(null); }} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void searchAddress("destination"); } }} placeholder="Enter a CBD address or landmark" />
                <button className="address-search-button" type="button" aria-label="Search destination address" title="Search destination address" onClick={() => void searchAddress("destination")} disabled={isSearchingLocations}>
                  {isSearchingLocations && locationSearchField === "destination" ? <LoaderCircle className="spin" size={18} /> : <Search size={18} />}
                </button>
              </div>
              {locationSearchField === "destination" ? <div className="address-results" role="listbox" aria-label="Destination address results">
                {isSearchingLocations ? <p>Searching addresses...</p> : null}
                {!isSearchingLocations && locationSearchError ? <p>{locationSearchError}</p> : null}
                {!isSearchingLocations && !locationSearchError ? locationSuggestions.map((location) => <button key={`${location.longitude}:${location.latitude}`} type="button" role="option" onClick={() => selectAddress("destination", location)}><MapPinned size={17} /><span><strong>{location.name}</strong><small>{location.display_name}</small></span></button>) : null}
              </div> : null}
            </div>
            <button className="plan-button" type="submit" disabled={isLoading} aria-label={isLoading ? "Finding routes" : "Find routes"}>
              {isLoading ? <LoaderCircle className="spin" size={19} /> : <Route size={19} />}
              <span>{isLoading ? "Finding routes" : "Find routes"}</span>
            </button>
          </form>

        <section className="route-sheet" aria-live="polite">
          {error ? <div className="notice notice-error"><AlertTriangle size={20} /><p>{error}</p></div> : null}
          {!error && result?.warning ? <div className="notice notice-warning"><AlertTriangle size={20} /><p>{result.warning}</p></div> : null}

          {result ? (
            <>
              <div className="results-heading">
                <div>
                  <span className="eyebrow">Route options</span>
                  <h2>{result.recommended_route_id ? "Crowd preference applied" : "Walking routes"}</h2>
                </div>
                <div className="result-actions">
                  {result.status === "available" ? <span className="status-chip available">Recent data</span> : null}
                  {activeRoute ? <button className={activeRouteIsSaved ? "save-route-button saved" : "save-route-button"} type="button" aria-label={activeRouteIsSaved ? "Route saved" : "Save current route"} title={activeRouteIsSaved ? "Route saved" : "Save current route"} onClick={saveActiveRoute}>
                    {activeRouteIsSaved ? <BookmarkCheck size={18} /> : <BookmarkPlus size={18} />}
                  </button> : null}
                </div>
              </div>
              {goRouteId !== null ? (
                <button type="button" className="show-all-routes-button" onClick={showAllRoutes}>Show all routes</button>
              ) : null}
              <div className="route-list">
                {visibleRoutes.map((route) => (
                  <div
                    key={route.route_id}
                    className={activeRouteId === route.route_id ? "route-option active" : "route-option"}
                    role="button"
                    tabIndex={0}
                    onClick={() => setActiveRouteId(route.route_id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setActiveRouteId(route.route_id);
                      }
                    }}
                  >
                    <span className={route.crowd_level ? `route-swatch ${route.crowd_level}` : "route-swatch unknown"} aria-hidden="true" />
                    <span className="route-main">
                      <strong>Route {route.route_id} - {routeLabel(route)}</strong>
                      <span>{formatDistance(route.distance_metres)} · {formatDuration(route.duration_seconds)}</span>
                    </span>
                    <span className={`coverage-chip ${confidenceTone(route)}`}>{confidenceLabel(route)}</span>
                    <button
                      type="button"
                      className="go-mark"
                      onClick={(event) => {
                        event.stopPropagation();
                        selectRouteAndGo(route.route_id);
                      }}
                    >
                      GO
                    </button>
                  </div>
                ))}
              </div>
              <p className="route-detail">Destination: {destination.label}.</p>
              <p className="route-detail">
                Data Coverage Confidence: {activeRoute?.data_coverage_confidence !== null && activeRoute?.data_coverage_confidence !== undefined ? `${activeRoute.data_coverage_confidence.toFixed(1)}%` : "N/A"}. Based on fresh nearby sensor coverage across total route distance.
              </p>
              {activeRoute?.crowd_score !== null && activeRoute?.crowd_score !== undefined ? <p className="route-detail">Peak nearby reading: {activeRoute.crowd_score} pedestrians per minute across {activeRoute.matched_sensor_count} nearby sensors.</p> : <p className="route-detail">Crowd levels are hidden until the latest official pedestrian data is within the 60-minute freshness window.</p>}
              {result.status === "available" && result.routes.some((route) => route.crowd_segments.length > 0) ? <p className="route-detail">Map colours show recent sensor coverage on every route: green low, orange medium, red high, and blue where no nearby sensor covers the path. The selected route is shown more strongly.</p> : null}
              {(nearbyTransit.start.length > 0 || nearbyTransit.destination.length > 0) ? (
                <div className="transit-summary">
                  <div><TrainFront size={17} /><strong>Public transport access</strong></div>
                  {nearbyTransit.start[0] ? <p>Near start: {nearbyTransit.start[0].name} ({nearbyTransit.start[0].mode}).</p> : null}
                  {nearbyTransit.destination[0] ? <p>Near destination: {nearbyTransit.destination[0].name} ({nearbyTransit.destination[0].mode}).</p> : null}
                </div>
              ) : null}
            </>
          ) : (
            <div className="empty-state"><Navigation size={22} /><div><h2>Plan a sensory-aware walk</h2><p>Search for Melbourne CBD addresses or landmarks at each end of your walk.</p></div></div>
          )}
        </section>

        </> : null}

        {activeView === "saved" ? <section className="sidebar-view"><div className="view-heading"><Bookmark size={21} /><div><h1>Saved routes</h1><p>{savedRoutes.length ? `${savedRoutes.length} route${savedRoutes.length === 1 ? "" : "s"}` : "No saved routes"}</p></div></div>{savedRoutes.length ? <div className="saved-route-list">{savedRoutes.map((savedRoute) => <div className="saved-route" key={savedRoute.id}><button type="button" onClick={() => restoreSavedRoute(savedRoute)}><strong>{savedRoute.startLabel} to {savedRoute.destinationLabel}</strong><span>{formatDistance(savedRoute.distanceMetres)} 路 {formatDuration(savedRoute.durationSeconds)} · {savedRoute.crowdLevel} preference</span></button><button type="button" className="remove-saved-route" aria-label={`Remove saved route to ${savedRoute.destinationLabel}`} title="Remove saved route" onClick={() => setSavedRoutes((routes) => routes.filter((route) => route.id !== savedRoute.id))}><Trash2 size={17} /></button></div>)}</div> : <div className="empty-state"><Bookmark size={22} /><div><h2>Nothing saved yet</h2><p>Save an active route after planning your walk.</p></div></div>}</section> : null}
        </aside>
      </section>

      {isDrawerOpen ? <><button className="drawer-backdrop" type="button" aria-label="Close navigation" onClick={() => setIsDrawerOpen(false)} /><aside className="navigation-drawer" role="dialog" aria-modal="true" aria-label="Navigation menu"><div className="drawer-header"><div className="brand-mark" aria-hidden="true"><Navigation size={19} fill="currentColor" /></div><strong>SensoryWay</strong><button className="icon-button" type="button" aria-label="Close navigation" title="Close navigation" onClick={() => setIsDrawerOpen(false)}><X size={20} /></button></div><div className="drawer-links"><button type="button" className={activeView === "explore" ? "drawer-link active" : "drawer-link"} onClick={() => selectView("explore")}><Compass size={20} />Explore</button><button type="button" className={activeView === "saved" ? "drawer-link active" : "drawer-link"} onClick={() => selectView("saved")}><Bookmark size={20} />Saved routes</button></div></aside></> : null}
    </main>
  );
}
