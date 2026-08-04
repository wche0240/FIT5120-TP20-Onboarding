"use client";

import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap, ZoomControl } from "react-leaflet";
import { useEffect } from "react";

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

const MELBOURNE_CBD: [number, number] = [-37.8136, 144.9631];

function routeColour(route: MapRoute, activeRouteId: number | null) {
  if (route.route_id === activeRouteId || route.recommended) return "#169b53";
  if (route.crowd_level === "high") return "#dc3f3f";
  if (route.crowd_level === "medium") return "#df8a16";
  return "#2d6cdf";
}

function transitColour(mode: TransitAccessPoint["mode"]) {
  return { bus: "#7e3af2", tram: "#d63384", train: "#1769e0", coach: "#7c5d20" }[mode];
}

function MapViewport({ routes, start, destination }: Pick<SensoryWayMapProps, "routes" | "start" | "destination">) {
  const map = useMap();

  useEffect(() => {
    const routePoints: [number, number][] = routes.flatMap((route) => route.coordinates.map((point) => [point.latitude, point.longitude] as [number, number]));
    const fallbackPoints: [number, number][] = [[start.latitude, start.longitude], [destination.latitude, destination.longitude]];
    const points: [number, number][] = routePoints.length > 1 ? routePoints : fallbackPoints;
    if (points.length > 1) map.fitBounds(points, { padding: [56, 56], maxZoom: 16 });
  }, [destination.latitude, destination.longitude, map, routes, start.latitude, start.longitude]);

  return null;
}

export default function SensoryWayMap({ start, destination, routes, transitAccessPoints, activeRouteId, onRouteSelect }: SensoryWayMapProps) {
  return (
    <MapContainer center={MELBOURNE_CBD} zoom={14} zoomControl={false} className="leaflet-map" aria-label="Melbourne CBD route map">
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <ZoomControl position="bottomright" />
      <MapViewport routes={routes} start={start} destination={destination} />
      {transitAccessPoints.map((accessPoint) => (
        <CircleMarker
          key={accessPoint.access_point_id}
          center={[accessPoint.latitude, accessPoint.longitude]}
          radius={4}
          pathOptions={{ color: "#ffffff", weight: 1.5, fillColor: transitColour(accessPoint.mode), fillOpacity: 0.9 }}
        >
          <Tooltip direction="top" offset={[0, -5]} opacity={0.96}>{accessPoint.name} ({accessPoint.mode})</Tooltip>
        </CircleMarker>
      ))}
      {routes.map((route) => (
        <Polyline
          key={route.route_id}
          positions={route.coordinates.map((point) => [point.latitude, point.longitude])}
          pathOptions={{ color: routeColour(route, activeRouteId), weight: route.route_id === activeRouteId ? 7 : 5, opacity: route.route_id === activeRouteId ? 1 : 0.7 }}
          eventHandlers={{ click: () => onRouteSelect(route.route_id) }}
        />
      ))}
      <CircleMarker center={[start.latitude, start.longitude]} radius={8} pathOptions={{ color: "#ffffff", weight: 3, fillColor: "#1769e0", fillOpacity: 1 }}>
        <Tooltip direction="top" offset={[0, -6]} opacity={1}>Start</Tooltip>
      </CircleMarker>
      <CircleMarker center={[destination.latitude, destination.longitude]} radius={8} pathOptions={{ color: "#ffffff", weight: 3, fillColor: "#d83f3f", fillOpacity: 1 }}>
        <Tooltip direction="top" offset={[0, -6]} opacity={1}>Destination</Tooltip>
      </CircleMarker>
    </MapContainer>
  );
}
