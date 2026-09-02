/**
 * The no-internet path.
 *
 * WHAT THIS CAN AND CANNOT DO
 * ---------------------------
 * It opens the phone's SMS composer with the message already written and the
 * gateway number filled in. The victim still has to press send.
 *
 * It CANNOT send silently. Expo has no API for that, and neither does iOS at
 * any price -- Apple has never allowed an app to send an SMS without the user
 * seeing it. On Android it is possible, but only with the SEND_SMS permission
 * and a native module, which means leaving Expo Go for a custom dev build and
 * a Play Store policy exemption.
 *
 * For a one-tap panic button that is a real limitation, so the UI says "Send by
 * SMS" rather than pretending the tap was the whole job.
 */
import { Linking, Platform } from 'react-native';

import { SMS_GATEWAY_NUMBER } from './config';
import { kindForTags } from './api';
import type { SosRow } from './queue';

/**
 * Build the body the server's parser actually understands.
 *
 * The exact shape matters -- it is matched by ingest/services/sms_parser.py:
 *
 *   HELP <hazard> <n> people at <lat>,<lon> <note>
 *
 * Two details are load-bearing, both verified against the parser:
 *   - the count must sit next to the word "people", or the headcount regex
 *     misses it and every report says 1 person;
 *   - the coordinates carry three or more decimals, which is what separates a
 *     position from something like "12.5 people".
 *
 * Coordinates are why this works at all offline: the pincode table is three
 * rows and landmark lookup needs the internet this path does without.
 */
export function buildSmsBody(row: SosRow): string {
  const hazard = kindForTags(row.tags).toLowerCase();
  const people = row.people ?? 1;

  const where =
    row.latitude != null && row.longitude != null
      ? ` at ${row.latitude.toFixed(4)},${row.longitude.toFixed(4)}`
      : '';

  const note = [row.customIssue, ...row.tags.filter((t) => t !== 'flood')]
    .filter(Boolean)
    .join(' ');

  // One SMS is 160 characters; anything past that is billed as two and may
  // arrive out of order. The note is the only expendable part, so it is what
  // gets cut.
  return `HELP ${hazard} ${people} people${where} ${note}`.trim().slice(0, 160);
}

/**
 * Open the composer, pre-filled.
 *
 * IN : row = SosRow
 * OUT: true if the composer opened -- NOT that the message was sent, which
 *      only the victim can decide.
 */
export async function openSmsComposer(row: SosRow): Promise<boolean> {
  const body = encodeURIComponent(buildSmsBody(row));
  // iOS wants & before body, Android wants ?. Getting this wrong opens the
  // composer with an empty message, which is worse than not opening it.
  const separator = Platform.OS === 'ios' ? '&' : '?';
  const url = `sms:${SMS_GATEWAY_NUMBER}${separator}body=${body}`;

  // Deliberately NOT gated on Linking.canOpenURL().
  //
  // Since Android 11, canOpenURL() answers false for any scheme the app has not
  // declared in its manifest <queries>, whether or not a messaging app exists.
  // Checking first therefore refuses to open a composer that would have worked
  // perfectly. Just attempt it, and report a real failure if one happens.
  try {
    await Linking.openURL(url);
    return true;
  } catch {
    return false;
  }
}
