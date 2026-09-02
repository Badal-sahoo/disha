/**
 * CAP warnings from the government feed.
 */
import { getList } from "@/shared/api/client";

/** GET /api/alerts -> [{id, identifier, event, severity, polygon, sent_at, active}], newest first. */
export function fetchAlerts(active = true, bbox = null) {
  const params = { active };
  if (bbox) params.bbox = [bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat].join(",");
  return getList("/alerts", { params });
}
