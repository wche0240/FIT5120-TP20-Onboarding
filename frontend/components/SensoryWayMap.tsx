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

function createTransitInfo(accessPoint: TransitAccessPoint) {
  const container = document.createElement("div");
  const name = document.createElement("strong");
  const details = document.createElement("div");

  name.textContent = accessPoint.name;
  details.textContent = `${accessPoint.mode} stop`;
  container.append(name, details);
  return container;
}

export default function SensoryWayMap({ start, destination, routes, transitAccessPoints, activeRouteId, onRouteSelect }: SensoryWayMapProps) {
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
        transitInfoRef.current?.setContent(createTransitInfo(accessPoint));
        transitInfoRef.current?.open({ map, anchor: marker });
      });
      nextOverlays.push(marker);
    });

    routes.forEach((route) => {
      const isActive = route.route_id === activeRouteId;
      const polyline = new google.maps.Polyline({
        map,
        path: route.coordinates.map(pointToLatLng),
        strokeColor: routeColour(route, activeRouteId),
        strokeOpacity: isActive ? 1 : 0.72,
        strokeWeight: isActive ? 7 : 5,
        zIndex: isActive ? 6 : 4,
      });
      polyline.addListener("click", () => onRouteSelect(route.route_id));
      nextOverlays.push(polyline);
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
  }, [activeRouteId, destination, isReady, onRouteSelect, routes, start, transitAccessPoints]);

  return (
    <>
      <div ref={mapElementRef} className="google-map" aria-label="Melbourne CBD route map" />
      {!isReady && <div className="map-loading" role="status">{loadError ?? "Loading Google Maps..."}</div>}
    </>
  );
}
