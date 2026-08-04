"use client";

import dynamic from "next/dynamic";
import {
  AlertTriangle,
  Bookmark,
  ChevronRight,
  CircleUserRound,
  Compass,
  ListFilter,
  LoaderCircle,
  MapPinned,
  Menu,
  Navigation,
  Route,
  Search,
  ShieldCheck,
  UsersRound,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import type { MapPoint, MapRoute } from "@/components/SensoryWayMap";

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

export default function HomePage() {
  const [startLabel, setStartLabel] = useState("Melbourne Central");
  const [destinationLabel, setDestinationLabel] = useState("Collins Street destination");
  const [crowdLevel, setCrowdLevel] = useState<CrowdLevel>("medium");
  const [result, setResult] = useState<RoutesResponse | null>(null);
  const [activeRouteId, setActiveRouteId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const start = findPlace(startLabel) ?? PLACES[0];
  const destination = findPlace(destinationLabel) ?? PLACES[4];
  const activeRoute = useMemo(() => result?.routes.find((route) => route.route_id === activeRouteId) ?? null, [activeRouteId, result]);

  async function planRoute(event?: FormEvent) {
    event?.preventDefault();
    const selectedStart = findPlace(startLabel);
    const selectedDestination = findPlace(destinationLabel);
    if (!selectedStart || !selectedDestination) {
      setError("Choose a start and destination from the Melbourne CBD suggestions.");
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
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
    } catch (requestError) {
      setResult(null);
      setActiveRouteId(null);
      setError(requestError instanceof Error ? requestError.message : "Could not plan a route.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <nav className="desktop-rail" aria-label="Primary navigation">
        <button className="icon-button rail-menu" aria-label="Open navigation"><Menu size={21} /></button>
        <div className="rail-links">
          <button className="rail-link is-active" aria-label="Explore routes"><Compass size={21} /><span>Explore</span></button>
          <button className="rail-link" aria-label="Saved routes"><Bookmark size={20} /><span>Saved</span></button>
        </div>
        <button className="icon-button" aria-label="Profile"><CircleUserRound size={23} /></button>
      </nav>

      <section className="map-stage" aria-label="Route planner">
        <SensoryWayMap start={start} destination={destination} routes={result?.routes ?? []} activeRouteId={activeRouteId} onRouteSelect={setActiveRouteId} />

        <header className="planner-header">
          <div className="brand-mark" aria-hidden="true"><Navigation size={19} fill="currentColor" /></div>
          <div className="brand-copy"><strong>SensoryWay</strong><span>Melbourne CBD</span></div>
          <button className="icon-button filter-button" aria-label="Route settings"><ListFilter size={20} /></button>
        </header>

        <form className="search-panel" onSubmit={planRoute}>
          <div className="place-field">
            <MapPinned size={18} aria-hidden="true" />
            <label htmlFor="start-place">Start</label>
            <input id="start-place" list="cbd-places" value={startLabel} onChange={(event) => setStartLabel(event.target.value)} placeholder="Choose a start point" />
          </div>
          <div className="field-divider" />
          <div className="place-field">
            <Search size={18} aria-hidden="true" />
            <label htmlFor="destination-place">Destination</label>
            <input id="destination-place" list="cbd-places" value={destinationLabel} onChange={(event) => setDestinationLabel(event.target.value)} placeholder="Choose a destination" />
          </div>
          <datalist id="cbd-places">{PLACES.map((place) => <option key={place.label} value={place.label}>{place.detail}</option>)}</datalist>
          <button className="plan-button" type="submit" disabled={isLoading} aria-label={isLoading ? "Finding routes" : "Find routes"}>
            {isLoading ? <LoaderCircle className="spin" size={19} /> : <Route size={19} />}
            <span>{isLoading ? "Finding routes" : "Find routes"}</span>
          </button>
        </form>

        <section className="preference-panel" aria-labelledby="preference-heading">
          <div className="panel-heading">
            <div className="heading-icon blue"><UsersRound size={19} /></div>
            <div>
              <h1 id="preference-heading">Crowd preference</h1>
              <p>Choose the highest crowd level you are comfortable with.</p>
            </div>
          </div>
          <div className="level-selector" role="radiogroup" aria-label="Maximum crowd level">
            {CROWD_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={crowdLevel === option.value ? "level-option selected" : "level-option"}
                onClick={() => setCrowdLevel(option.value)}
                role="radio"
                aria-checked={crowdLevel === option.value}
              >
                <strong>{option.label}</strong><span>{option.help}</span>
              </button>
            ))}
          </div>
        </section>

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
                <span className={result.status === "available" ? "status-chip available" : "status-chip stale"}>{result.status === "available" ? "Current data" : "Crowd data delayed"}</span>
              </div>
              <div className="route-list">
                {result.routes.map((route) => (
                  <button key={route.route_id} className={activeRouteId === route.route_id ? "route-option active" : "route-option"} onClick={() => setActiveRouteId(route.route_id)}>
                    <span className={route.crowd_level ? `route-swatch ${route.crowd_level}` : "route-swatch unknown"} aria-hidden="true" />
                    <span className="route-main">
                      <strong>Route {route.route_id} - {routeLabel(route)}</strong>
                      <span>{formatDistance(route.distance_metres)} · {formatDuration(route.duration_seconds)}</span>
                    </span>
                    {route.recommended ? <span className="recommended-mark"><ShieldCheck size={17} />Recommended</span> : <ChevronRight size={19} aria-hidden="true" />}
                  </button>
                ))}
              </div>
              {activeRoute?.crowd_score !== null && activeRoute?.crowd_score !== undefined ? <p className="route-detail">Peak nearby reading: {activeRoute.crowd_score} pedestrians per minute across {activeRoute.matched_sensor_count} nearby sensors.</p> : <p className="route-detail">Crowd levels are hidden until the latest official pedestrian data is within the 30-minute freshness window.</p>}
            </>
          ) : (
            <div className="empty-state"><Navigation size={22} /><div><h2>Plan a sensory-aware walk</h2><p>Choose two Melbourne CBD places, then compare route options by crowd level.</p></div></div>
          )}
        </section>

        <div className="map-tools"><button className="icon-button" aria-label="Centre map on route"><Navigation size={19} /></button></div>
      </section>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        <button className="mobile-link is-active"><Compass size={21} /><span>Explore</span></button>
        <button className="mobile-link"><Bookmark size={21} /><span>Saved</span></button>
        <button className="mobile-link"><CircleUserRound size={21} /><span>Profile</span></button>
      </nav>
    </main>
  );
}
