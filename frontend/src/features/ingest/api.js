/**
 * SMS triage -- the messages a human still has to deal with.
 */
import { getList } from "@/shared/api/client";

/**
 * GET /api/sms/unparsed
 *
 * OUT: Promise<[{id, from_number, body, received_at, parsed, confidence, incident}]>
 *
 * Two kinds of message come back: ones the parser could not place at all
 * (incident is null), and ones it placed but was unsure about.
 */
export function fetchUnparsedSms() {
  return getList("/sms/unparsed");
}
