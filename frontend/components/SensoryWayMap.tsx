"use client";

import { importLibrary, setOptions } from "@googlemaps/js-api-loader";
import { useEffect, useRef, useState } from "react";

export type MapPoint = {
  latitude: number;
  longitude: number;
};

export type MapRoute = {
  route_id: number;
  coordinates: MapPoint[];
  crowd_level: "low" | "medium" | "high" | null;
  crowd_segments: Array<{
    coordinates: MapPoint[];
    crowd_level: "low" | "medium" | "high" | null;
    crowd_score: number | null;
    matched_sensor_count: number;
  }>;
  recommended: boolean;
};

export type TransitAccessPoint = MapPoint & {
  access_point_id: string;
  name: string;
  mode: "bus" | "tram" | "train" | "coach";
  source_mode: string;
  distance_metres: number | null;
};

type SensoryWayMapProps = {
  start: MapPoint;
  destination: MapPoint;
  routes: MapRoute[];
  transitAccessPoints: TransitAccessPoint[];
  activeRouteId: number | null;
  onRouteSelect: (routeId: number) => void;
  onTransitPointSelect: (field: "start" | "destination", accessPoint: TransitAccessPoint) => void;
};

type MapOverlay = google.maps.Marker | google.maps.Polyline;

const MELBOURNE_CBD = { lat: -37.8136, lng: 144.9631 };
const GOOGLE_MAPS_API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;

let mapsLibraryPromise: Promise<google.maps.MapsLibrary> | null = null;

function loadMapsLibrary(apiKey: string) {
  if (!mapsLibraryPromise) {
    setOptions({ key: apiKey, v: "weekly", language: "en", region: "AU" });
    mapsLibraryPromise = importLibrary("maps");
  }

  return mapsLibraryPromise;
}

function routeColour(route: MapRoute, activeRouteId: number | null) {
  if (route.route_id === activeRouteId || route.recommended) return "#169b53";
  if (route.crowd_level === "high") return "#dc3f3f";
  if (route.crowd_level === "medium") return "#df8a16";
  return "#2d6cdf";
}

function segmentColour(crowdLevel: "low" | "medium" | "high") {
  return { low: "#188038", medium: "#f9ab00", high: "#d93025" }[crowdLevel];
}

function segmentOutlineColour(crowdLevel: "low" | "medium" | "high") {
  return { low: "#0b5c31", medium: "#a66300", high: "#a71c18" }[crowdLevel];
}

function routeOutlineColour(route: MapRoute, activeRouteId: number | null) {
  if (route.crowd_segments.length > 0) return "#1a4f9c";
  if (route.route_id === activeRouteId || route.recommended) return "#0b6e39";
  if (route.crowd_level === "high") return "#9f251f";
  if (route.crowd_level === "medium") return "#9b5900";
  return "#1a4f9c";
}

function transitColour(mode: TransitAccessPoint["mode"]) {
  return { bus: "#7e3af2", tram: "#d63384", train: "#1769e0", coach: "#7c5d20" }[mode];
}

function pointToLatLng(point: MapPoint) {
  return { lat: point.latitude, lng: point.longitude };
}

function markerIcon(fillColor: string, scale: number): google.maps.Symbol {
  return {
    path: google.maps.SymbolPath.CIRCLE,
    fillColor,
    fillOpacity: 1,
    scale,
    strokeColor: "#ffffff",
    strokeWeight: 2,
  };
}

function createTransitInfo(accessPoint: TransitAccessPoint, onSelect: (field: "start" | "destination") => void) {
  const container = document.createElement("div");
  const actions = document.createElement("div");
  const name = document.createElement("strong");
  const details = document.createElement("div");
  const startButton = document.createElement("button");
  const destinationButton = document.createElement("button");

  container.className = "transit-info-window";
  actions.className = "transit-info-actions";
  name.textContent = accessPoint.name;
  details.textContent = `${accessPoint.mode} stop`;
  startButton.type = "button";
  startButton.textContent = "Set as start";
  startButton.setAttribute("aria-label", `Set ${accessPoint.name} as start`);
  startButton.addEventListener("click", () => onSelect("start"));
  destinationButton.type = "button";
  destinationButton.textContent = "Set as destination";
  destinationButton.setAttribute("aria-label", `Set ${accessPoint.name} as destination`);
  destinationButton.addEventListener("click", () => onSelect("destination"));
  actions.append(startButton, destinationButton);
  container.append(name, details, actions);
  return container;
}

export default function SensoryWayMap({ start, destination, routes, transitAccessPoints, activeRouteId, onRouteSelect, onTransitPointSelect }: SensoryWayMapProps) {
  const mapElementRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<google.maps.Map | null>(null);
  const overlaysRef = useRef<MapOverlay[]>([]);
  const transitInfoRef = useRef<google.maps.InfoWindow | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!GOOGLE_MAPS_API_KEY) {
      setLoadError("Google Maps is not configured. Add NEXT_PUBLIC_GOOGLE_MAPS_API_KEY to frontend/.env.local.");
      return;
    }

    let cancelled = false;

    loadMapsLibrary(GOOGLE_MAPS_API_KEY)
      .then(({ Map }) => {
        if (cancelled || !mapElementRef.current) return;

        mapRef.current = new Map(mapElementRef.current, {
          center: MELBOURNE_CBD,
          zoom: 14,
          fullscreenControl: false,
          mapTypeControl: false,
          streetViewControl: false,
          zoomControlOptions: { position: google.maps.ControlPosition.RIGHT_BOTTOM },
        });
        transitInfoRef.current = new google.maps.InfoWindow();
        setIsReady(true);
      })
      .catch(() => {
        if (!cancelled) setLoadError("Google Maps could not load. Check the API key, billing status, and website restrictions.");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isReady) return;

    overlaysRef.current.forEach((overlay) => overlay.setMap(null));
    const nextOverlays: MapOverlay[] = [];

    transitAccessPoints.forEach((accessPoint) => {
      const marker = new google.maps.Marker({
        map,
        position: pointToLatLng(accessPoint),
        title: `${accessPoint.name} (${accessPoint.mode})`,
        icon: markerIcon(transitColour(accessPoint.mode), 4),
        zIndex: 2,
      });

      marker.addListener("click", () => {
        transitInfoRef.current?.setContent(createTransitInfo(accessPoint, (field) => {
          onTransitPointSelect(field, accessPoint);
          transitInfoRef.current?.close();
        }));
        transitInfoRef.current?.open({ map, anchor: marker });
      });
      nextOverlays.push(marker);
    });

    routes.forEach((route) => {
      const isActive = route.route_id === activeRouteId;
      const path = route.coordinates.map(pointToLatLng);
      const routeFill = route.crowd_segments.length > 0 ? "#4285f4" : routeColour(route, activeRouteId);
      const baseOpacity = isActive ? 1 : 0.6;
      const baseWeight = isActive ? 6 : 4;

      // A light halo and dark outline keep routes readable over detailed map tiles.
      const routeHalo = new google.maps.Polyline({
        map,
        path,
        strokeColor: "#ffffff",
        strokeOpacity: isActive ? 0.92 : 0.64,
        strokeWeight: baseWeight + 6,
        zIndex: isActive ? 3 : 1,
      });
      const routeOutline = new google.maps.Polyline({
        map,
        path,
        strokeColor: routeOutlineColour(route, activeRouteId),
        strokeOpacity: baseOpacity,
        strokeWeight: baseWeight + 3,
        zIndex: isActive ? 4 : 2,
      });
      const polyline = new google.maps.Polyline({
        map,
        path,
        strokeColor: routeFill,
        strokeOpacity: baseOpacity,
        strokeWeight: baseWeight,
        zIndex: isActive ? 5 : 3,
      });
      [routeHalo, routeOutline, polyline].forEach((overlay) => {
        overlay.addListener("click", () => onRouteSelect(route.route_id));
        nextOverlays.push(overlay);
      });

      route.crowd_segments.forEach((segment) => {
        if (!segment.crowd_level) return;
        const segmentWeight = isActive ? 6 : 4;
        const segmentOpacity = isActive ? 1 : 0.78;
        const segmentPath = segment.coordinates.map(pointToLatLng);
        const segmentOutline = new google.maps.Polyline({
          map,
          path: segmentPath,
          strokeColor: segmentOutlineColour(segment.crowd_level),
          strokeOpacity: segmentOpacity,
          strokeWeight: segmentWeight + 3,
          zIndex: isActive ? 6 : 4,
        });
        const segmentPolyline = new google.maps.Polyline({
          map,
          path: segmentPath,
          strokeColor: segmentColour(segment.crowd_level),
          strokeOpacity: segmentOpacity,
          strokeWeight: segmentWeight,
          zIndex: isActive ? 7 : 5,
        });
        [segmentOutline, segmentPolyline].forEach((overlay) => {
          overlay.addListener("click", () => onRouteSelect(route.route_id));
          nextOverlays.push(overlay);
        });
      });
    });

    nextOverlays.push(
      new google.maps.Marker({ map, position: pointToLatLng(start), title: "Start", icon: markerIcon("#1769e0", 8), zIndex: 10 }),
      new google.maps.Marker({ map, position: pointToLatLng(destination), title: "Destination", icon: markerIcon("#d83f3f", 8), zIndex: 10 }),
    );

    const routePoints = routes.flatMap((route) => route.coordinates);
    const pointsToFit = routePoints.length > 1 ? routePoints : [start, destination];
    if (pointsToFit.length > 1) {
      const bounds = new google.maps.LatLngBounds();
      pointsToFit.forEach((point) => bounds.extend(pointToLatLng(point)));
      map.fitBounds(bounds, 56);
    }

    overlaysRef.current = nextOverlays;

    return () => {
      nextOverlays.forEach((overlay) => overlay.setMap(null));
    };
  }, [activeRouteId, destination, isReady, onRouteSelect, onTransitPointSelect, routes, start, transitAccessPoints]);

  return (
    <>
      <div ref={mapElementRef} className="google-map" aria-label="Melbourne CBD route map" />
      {!isReady && <div className="map-loading" role="status">{loadError ?? "Loading Google Maps..."}</div>}
    </>
  );
}
