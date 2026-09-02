/**
 * The internet path: POST the SOS straight to the dispatch server.
 *
 * Plain fetch, no HTTP library. One endpoint and a login is not worth a
 * dependency, and every kilobyte matters on a phone that may be on 2G.
 */
import { API_BASE, APP_ACCOUNT, REQUEST_TIMEOUT_MS } from './config';
import type { SosRow } from './queue';

/** Kept in memory only. A cold start just logs in again -- it costs one request. */
let accessToken: string | null = null;

/** fetch() has no timeout of its own; without this a dead network hangs forever. */
async function withTimeout(url: string, init: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function login(): Promise<string> {
  const response = await withTimeout(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(APP_ACCOUNT),
  });
  if (!response.ok) throw new Error(`login failed (${response.status})`);
  const data = await response.json();
  accessToken = data.access;
  return data.access;
}

/**
 * The app's four tags versus the three hazard kinds the engine solves for.
 *
 * REQUIRED_CAPS in dispatch/engine.py keys off this, so a wrong kind is not
 * cosmetic -- it decides which units are even allowed to be sent. Anything that
 * is not obviously water is filed as CYCLONE, which is the broadest: it accepts
 * HIGH_CLEARANCE, MEDICAL or ROPE_RESCUE.
 */
export function kindForTags(tags: string[]): 'FLOOD' | 'CYCLONE' | 'LANDSLIDE' {
  if (tags.includes('flood')) return 'FLOOD';
  return 'CYCLONE';
}

/**
 * Severity 1..5 from what the victim tapped.
 *
 * Severity is 45% of the dispatch priority -- the single heaviest term -- so
 * this is not decoration. Someone trapped or hurt outranks someone asking
 * where the shelter is.
 */
export function severityForTags(tags: string[]): number {
  if (tags.includes('trapped') || tags.includes('medical')) return 5;
  if (tags.includes('flood')) return 4;
  if (tags.includes('shelter')) return 2;
  return 3;
}

/** The human-readable half, so an operator reads words and not tag ids. */
export function describe(row: SosRow): string {
  const parts: string[] = [];
  if (row.tags.length) parts.push(row.tags.join(', '));
  if (row.customIssue) parts.push(row.customIssue);
  if (row.accuracy != null) parts.push(`GPS ±${Math.round(row.accuracy)} m`);
  return parts.join(' — ') || 'SOS from the DISHA app';
}

/**
 * POST one queued SOS as an incident.
 *
 * IN : row = SosRow  -- must carry a position; the server refuses a pin at 0,0
 * OUT: the created incident, including its INC**** code
 *
 * eventId goes up as client_ref, which is what makes retrying safe: the server
 * returns the SAME incident for a repeated client_ref instead of dropping a
 * second pin. That is why the queue can flush blindly after a signal returns.
 */
export async function postReport(row: SosRow): Promise<{ code: string }> {
  if (row.latitude == null || row.longitude == null) {
    throw new Error('no position -- use the SMS path');
  }

  const body = JSON.stringify({
    client_ref: row.eventId,
    lat: row.latitude,
    lon: row.longitude,
    kind: kindForTags(row.tags),
    severity: severityForTags(row.tags),
    people: row.people ?? 1,
    description: describe(row),
    accuracy_m: row.accuracy,
  });

  const send = (token: string) =>
    withTimeout(`${API_BASE}/reports`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body,
    });

  let response = await send(accessToken ?? (await login()));

  // The 60-minute access token expired while the phone was offline. One retry.
  if (response.status === 401) {
    response = await send(await login());
  }

  if (!response.ok) {
    throw new Error(`report rejected (${response.status})`);
  }
  return response.json();
}

export type Rescue = {
  status: string;            // OPEN | ASSIGNED | RESOLVED
  unitCode: string | null;   // "BOAT-04"
  etaMin: number | null;
  shelterCode: string | null;
  assignmentStatus: string | null;  // DISPATCHED | EN_ROUTE | ON_SCENE | ...
};

/**
 * Ask the server what has happened to a report we filed.
 *
 * GET /api/reports/{code} returns the incident WITH its assignments, which is
 * the whole round trip in one call: whether the control room has it, and
 * whether a unit has been put on it.
 *
 * This is what turns the app from a postbox into something a frightened person
 * can actually read: "help is coming, BOAT-04, 12 minutes" instead of silence.
 */
export async function fetchRescue(code: string): Promise<Rescue> {
  const response = await withTimeout(`${API_BASE}/reports/${encodeURIComponent(code)}`, {
    method: 'GET',
    headers: { Authorization: `Bearer ${accessToken ?? (await login())}` },
  });
  if (!response.ok) throw new Error(`status check failed (${response.status})`);
  const data = await response.json();

  // Only work that is actually under way. A PROPOSED row is a preview nobody
  // has been told about, so promising rescue on the strength of one would be
  // a lie to someone on a roof.
  const live = (data.assignments ?? []).filter(
    (a: { status: string }) => a.status !== 'PROPOSED' && a.status !== 'COMPLETE',
  );
  const chosen = live[0] ?? null;

  return {
    status: data.status,
    unitCode: chosen?.resource_code ?? null,
    etaMin: chosen?.eta_min ?? null,
    shelterCode: chosen?.shelter_code ?? null,
    assignmentStatus: chosen?.status ?? null,
  };
}

/** Cheap liveness probe, so the UI can say "online" before anyone taps SOS. */
export async function serverReachable(): Promise<boolean> {
  try {
    // 401 is a perfectly good answer here: something is listening and routing.
    const response = await withTimeout(`${API_BASE}/state`, { method: 'GET' });
    return response.status > 0;
  } catch {
    return false;
  }
}
