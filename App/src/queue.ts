/**
 * The offline queue: every SOS is written to disk BEFORE anything is attempted.
 *
 * That order is the whole design. A phone in a flood loses signal mid-request,
 * runs out of battery, or gets dropped in water. Whatever happens to the
 * network, the tap is already durable, and the queue can be flushed later --
 * or read out loud off the screen to a rescuer if it comes to that.
 *
 * Extracted from HomeScreen so the sync logic has somewhere to live that is not
 * a 700-line component.
 */
import * as SQLite from 'expo-sqlite';

import { postReport } from './api';

export type SosStatus = 'queued' | 'pending_sms_fallback' | 'sent' | 'failed';

export type SosRow = {
  id?: number;
  eventId: string;
  createdAt: string;
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  tags: string[];
  customIssue: string | null;
  people?: number;
  status: SosStatus;
};

const DB_NAME = 'resq_offline_queue.db';
let databasePromise: Promise<SQLite.SQLiteDatabase> | null = null;

export async function getDatabase(): Promise<SQLite.SQLiteDatabase> {
  if (!databasePromise) {
    databasePromise = SQLite.openDatabaseAsync(DB_NAME);
  }
  const db = await databasePromise;

  await db.execAsync(`
    PRAGMA journal_mode = WAL;
    CREATE TABLE IF NOT EXISTS sos_queue (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id TEXT NOT NULL UNIQUE,
      created_at TEXT NOT NULL,
      latitude REAL,
      longitude REAL,
      accuracy REAL,
      tags_json TEXT NOT NULL,
      custom_issue TEXT,
      status TEXT NOT NULL,
      retry_count INTEGER NOT NULL DEFAULT 0,
      synced_at TEXT
    );
  `);

  // Added after the first build shipped, so it has to be tolerated as missing.
  // people is 25% of the dispatch priority -- worth carrying.
  try {
    await db.execAsync('ALTER TABLE sos_queue ADD COLUMN people INTEGER NOT NULL DEFAULT 1');
  } catch {
    /* already there */
  }

  // The server code, once we have one, so the victim can be told INC0042.
  try {
    await db.execAsync('ALTER TABLE sos_queue ADD COLUMN incident_code TEXT');
  } catch {
    /* already there */
  }

  return db;
}

export function createEventId(): string {
  return `sos_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

/** Write the SOS down. Returns the queue row, ready to send. */
export async function enqueue(row: SosRow): Promise<SosRow> {
  const db = await getDatabase();
  const result = await db.runAsync(
    `INSERT INTO sos_queue (
      event_id, created_at, latitude, longitude, accuracy,
      tags_json, custom_issue, status, people
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      row.eventId,
      row.createdAt,
      row.latitude,
      row.longitude,
      row.accuracy,
      JSON.stringify(row.tags),
      row.customIssue,
      row.status,
      row.people ?? 1,
    ],
  );
  return { ...row, id: Number(result.lastInsertRowId) };
}

type DbRow = {
  id: number;
  event_id: string;
  created_at: string;
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  tags_json: string;
  custom_issue: string | null;
  status: SosStatus;
  people: number | null;
};

function toSosRow(r: DbRow): SosRow {
  let tags: string[] = [];
  try {
    tags = JSON.parse(r.tags_json);
  } catch {
    /* a corrupt tag blob must not stop the SOS going out */
  }
  return {
    id: r.id,
    eventId: r.event_id,
    createdAt: r.created_at,
    latitude: r.latitude,
    longitude: r.longitude,
    accuracy: r.accuracy,
    tags,
    customIssue: r.custom_issue,
    people: r.people ?? 1,
    status: r.status,
  };
}

/** Everything not yet accepted by the server, oldest first. */
export async function pending(): Promise<SosRow[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<DbRow>(
    `SELECT * FROM sos_queue
     WHERE status IN ('queued', 'pending_sms_fallback', 'failed')
     ORDER BY created_at ASC`,
  );
  return rows.map(toSosRow);
}

export async function pendingCount(): Promise<number> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<{ count: number }>(
    `SELECT COUNT(*) AS count FROM sos_queue
     WHERE status IN ('queued', 'pending_sms_fallback', 'failed')`,
  );
  return rows[0]?.count ?? 0;
}

async function markSent(id: number, code: string) {
  const db = await getDatabase();
  await db.runAsync(
    "UPDATE sos_queue SET status = 'sent', synced_at = ?, incident_code = ? WHERE id = ?",
    [new Date().toISOString(), code, id],
  );
}

async function markFailed(id: number) {
  const db = await getDatabase();
  await db.runAsync(
    "UPDATE sos_queue SET status = 'failed', retry_count = retry_count + 1 WHERE id = ?",
    [id],
  );
}

/**
 * Try to deliver everything waiting.
 *
 * OUT: {sent, failed, needsSms} -- needsSms are the ones with no position,
 *      which the server would refuse anyway; those are the SMS path's job.
 *
 * Safe to call as often as you like. client_ref makes a repeated POST return
 * the SAME incident rather than a duplicate pin, so a flush that half-succeeded
 * and got interrupted simply finishes next time.
 */
export async function flush(): Promise<{ sent: number; failed: number; needsSms: number }> {
  const rows = await pending();
  let sent = 0;
  let failed = 0;
  let needsSms = 0;

  for (const row of rows) {
    if (row.latitude == null || row.longitude == null) {
      needsSms += 1;
      continue;
    }
    try {
      const incident = await postReport(row);
      await markSent(row.id!, incident.code);
      sent += 1;
    } catch {
      await markFailed(row.id!);
      failed += 1;
      // One dead network fails all of them; stop hammering it.
      break;
    }
  }

  return { sent, failed, needsSms };
}
