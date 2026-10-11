export type IncidentType = 'rescue' | 'food' | 'medical' | 'shelter' | 'info' | 'animal_attack' | 'other';
export type UrgencyBand = 'critical' | 'high' | 'medium' | 'low';
export type HazardType = 'water_rising' | 'stranded' | 'injury' | 'none' | 'unknown';
export type RequestStatus = 'new' | 'needs_recheck' | 'matched' | 'approved' | 'in_progress' | 'resolved' | 'closed';

export interface VulnerableFlags {
  child: boolean;
  elderly: boolean;
  disabled: boolean;
  pregnant: boolean;
  medical_need: boolean;
}

export interface ExtractedRequest {
  type: IncidentType;
  place_text: string | null;
  people: {
    count: number | null;
    confidence: number;
  };
  vulnerable: VulnerableFlags;
  hazard: HazardType;
  urgency_hint: UrgencyBand;
  language: 'hi' | 'hinglish' | 'en' | 'ta';
  is_update_phrase: boolean;
  confidence: {
    type: number;
    place: number;
    people: number;
    vulnerable: number;
    urgency: number;
  };
  evidence_spans: Record<string, string>;
  notes: string;
  needs_human_review?: boolean;
}

export interface DedupeDecision {
  decision: 'new' | 'duplicate' | 'update' | 'conflict';
  target_request_id: string | null;
  changed_fields?: Record<string, any>;
  evidence: string[];
  confidence: number;
}

export interface Explanation {
  text_en: string;
  text_hi: string;
}

export interface ConfirmationCardData {
  incident_type: string;
  place_text: string | null;
  people_count: number | null;
  vulnerable: Record<string, boolean>;
  hazard: string;
  summary: string;
  safety_line?: string;
  ready_to_submit: boolean;
}

export interface ChatTurnResponse {
  session_id: string;
  bot_message: string;
  turn_count: number;
  missing_fields: string[];
  confirmation_card?: ConfirmationCardData;
  safety_line?: string;
}

export interface ScenarioTile {
  id: string;
  label_en: string;
  label_hi?: string;
  incident_type: string;
  icon: string;
}

export interface ScenarioConfig {
  id: string;
  title: string;
  description: string;
  incident_types: string[];
  tiles: ScenarioTile[];
  follow_up_questions: Record<string, Record<string, string>>;
  urgency_rules: Record<string, number>;
  resource_types: string[];
  safety_line_ids: string[];
}

export interface ReportSubmitRequest {
  text: string;
  channel?: 'text' | 'voice';
  lang?: string;
  source_id?: string;
  location_pin?: { lat: number; lng: number };
  scenario_id?: string;
}

export interface ReportSubmitResponse {
  report_id: string;
  request_id: string;
  status_token: string;
  summary: string;
  urgency_score: number;
  dedupe_decision: string;
  flags: string[];
  safety_line: string;
}

export interface UrgencyWeights {
  version: number;
  w_vulnerability: number;
  w_people: number;
  w_hazard: number;
  w_wait_time: number;
  confidence_discount_factor: number;
}
