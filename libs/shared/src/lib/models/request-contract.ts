import { ConfirmationCardData } from './request.model';

const VULNERABLE_KEYS = ['child', 'elderly', 'disabled', 'pregnant', 'medical_need'] as const;

export interface CanonicalRequest {
  hazard: string;
  lang: string;
  lat: number | null;
  lng: number | null;
  pack_id: string;
  people_count: number | null;
  place_text: string | null;
  summary: string;
  type: string;
  vulnerable: Record<string, boolean>;
}

export function buildCanonicalRequest(input: {
  card: ConfirmationCardData;
  lang: string;
  locationPin?: { lat: number; lng: number } | null;
  scenarioId?: string;
}): CanonicalRequest {
  const vulnerable: Record<string, boolean> = {};
  for (const key of VULNERABLE_KEYS) {
    vulnerable[key] = !!input.card.vulnerable?.[key];
  }
  const pin = input.locationPin;
  return {
    hazard: input.card.hazard,
    lang: input.lang,
    lat: pin ? Number(pin.lat.toFixed(6)) : null,
    lng: pin ? Number(pin.lng.toFixed(6)) : null,
    pack_id: input.scenarioId || 'flood',
    people_count: input.card.people_count,
    place_text: input.card.place_text,
    summary: input.card.summary,
    type: input.card.incident_type,
    vulnerable,
  };
}

export function canonicalRequestJson(input: {
  card: ConfirmationCardData;
  lang: string;
  locationPin?: { lat: number; lng: number } | null;
  scenarioId?: string;
}): string {
  return JSON.stringify(buildCanonicalRequest(input));
}
