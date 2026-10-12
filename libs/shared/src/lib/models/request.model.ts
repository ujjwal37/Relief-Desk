export type IncidentType = 'rescue' | 'food' | 'medical' | 'shelter' | 'info' | 'animal_attack' | 'other';
export type UrgencyBand = 'critical' | 'high' | 'medium' | 'low';
export type HazardType = 'water_rising' | 'stranded' | 'injury' | 'none' | 'unknown';
export type RequestStatus = 'new' | 'needs_recheck' | 'matched' | 'approved' | 'dispatched' | 'in_progress' | 'resolved' | 'completed' | 'closed';

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

export interface StructuredReportFacts {
  incident_type: string;
  place_text: string | null;
  people_count: number | null;
  vulnerable: Record<string, boolean>;
  hazard: string;
  summary: string;
}

export interface ReportSubmitRequest {
  text: string;
  channel?: 'text' | 'voice' | 'form';
  lang?: string;
  source_id?: string;
  location_pin?: { lat: number; lng: number };
  scenario_id?: string;
  structured?: StructuredReportFacts;
  /** Client retry key. The server returns the original request when this repeats. */
  idempotency_key?: string;
  /** Citizen's own words, kept separate from the machine summary. */
  raw_text?: string;
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

export interface StoredRequest {
  id: string;
  event_id?: string;
  pack_id?: string;
  type: IncidentType;
  place_text: string | null;
  ward_id: string | null;
  lat: number | null;
  lng: number | null;
  people_count: number | null;
  vulnerable: VulnerableFlags;
  hazard: HazardType;
  urgency_score: number;
  urgency_reason: string;
  wait_points?: number | null;
  wait_minutes?: number | null;
  status: RequestStatus;
  confidence?: {
    type: number;
    place: number;
    people: number;
    vulnerable: number;
    urgency: number;
  };
  report_ids?: string[];
  cluster_id?: string | null;
  merged_into?: string | null;
  flags?: string[];
  raw_text?: string | null;
  ai_translation?: string | null;
  /** "gemini" live, "recorded" cache, or "offline_fallback". */
  ai_source?: 'gemini' | 'recorded' | 'offline_fallback';
  ai?: {
    provider: 'gemini' | 'cache' | 'fallback';
    model?: string | null;
    latency_ms?: number;
    tokens?: number | null;
    cached?: boolean;
    fallback_reason?: string | null;
  };
  translations?: { [lang: string]: string };
  translation_confidence?: number;
  assigned_resource_id?: string | null;
  reserved_people?: number | null;
  merged_count?: number;
  analysis_status?: 'analysing' | 'complete';
  trace?: Array<{
    agent: string;
    status: string;
    input_summary?: string;
    output?: string;
    model?: string;
    latency_ms?: number;
    tokens?: number | null;
    tool_calls?: string[];
    ts?: string;
  }>;
  update_count?: number;
  created_at?: string;
  updated_at?: string;
}

export interface StoredResource {
  id: string;
  kind: 'boat' | 'shelter' | 'food' | 'medical';
  name: string;
  name_hi?: string;
  ward_id: string;
  lat: number;
  lng: number;
  capacity_total: number;
  capacity_remaining: number;
  status: 'available' | 'busy' | 'dispatched' | 'accepted' | 'en_route' | 'on_scene' | 'returning' | 'depleted' | 'off_duty';
  location_updated_at?: string | null;
  assigned_request_id?: string | null;
  area_name?: string | null;
  simulated?: boolean;
  location_source?: 'seed' | 'gps' | 'simulated' | 'coordinator' | string;
  heading?: number | null;
  speed_mps?: number | null;
  accuracy_m?: number | null;
  status_changed_at?: string | null;
  busy_since?: string | null;
  share_token?: string;
  location_trail?: { lat: number; lng: number; at: string }[];
}

export interface TeamFix {
  lat: number;
  lng: number;
  accuracy?: number | null;
  heading?: number | null;
  speed?: number | null;
  ts?: string | null;
  token?: string;
}

export interface TeamLive {
  id: string;
  name: string;
  kind: 'boat' | 'medical' | 'food' | 'shelter' | string;
  status: string;
  lat: number;
  lng: number;
  heading?: number | null;
  speed?: number | null;
  accuracy?: number | null;
  updated_at?: string | null;
  stale: boolean;
  simulated: boolean;
  source: string;
  assigned_request_id?: string | null;
  case_lat?: number | null;
  case_lng?: number | null;
  distance_km?: number | null;
  eta_minutes?: number | null;
  no_nearby: boolean;
  trail: { lat: number; lng: number; at?: string }[];
  check_in: boolean;
  busy_minutes?: number | null;
  status_changed_at?: string | null;
  busy_since?: string | null;
  soon_free: boolean;
  share_token: string;
}

export interface CitizenTrack {
  visible: boolean;
  state: 'hidden' | 'dispatched' | 'arrived' | 'completed' | string;
  team_name?: string | null;
  team_kind?: string | null;
  distance_km?: number | null;
  eta_minutes?: number | null;
  no_nearby: boolean;
  lat?: number | null;
  lng?: number | null;
  case_lat?: number | null;
  case_lng?: number | null;
  updated_at?: string | null;
  simulated: boolean;
  stale: boolean;
  trail: { lat: number; lng: number }[];
}

export interface MatchBreakdown {
  distance_km: number;
  distance_score: number;
  capacity_fit_score: number;
  urgency_score: number;
  vulnerability_fit_score: number;
  total_score: number;
}

export interface MatchProposal {
  match_id: string;
  request_id: string;
  resource_id: string;
  resource_name: string;
  resource_kind: string;
  resource_ward: string;
  capacity_total: number;
  capacity_remaining: number;
  score: number;
  breakdown: MatchBreakdown;
  explanation?: string;
  explanation_hi?: string;
  state: 'proposed' | 'approved' | 'rejected';
  is_fallback?: boolean;
  fallback_label?: string | null;
  simulated?: boolean;
  eta_minutes?: number | null;
  no_nearby?: boolean;
  wait_minutes?: number | null;
  wait_team_name?: string | null;
  overcommit_warning: boolean;
  soon_free?: boolean;
}

export interface StoredCluster {
  id: string;
  request_ids: string[];
  evidence: string[];
  merged_by: string;
  undone: boolean;
  created_at?: string;
}

export interface PublicCell {
  cell_id: string;
  ward: string;
  center_lat: number;
  center_lng: number;
  incident_counts: { [type: string]: number };
  total_reports: number;
  severity_band: 'critical' | 'high' | 'medium' | 'low';
  time_bucket: string;
  active_hazard?: string | null;
  alerts: string[];
  last_updated: string;
}

export interface PublicCellsResponse {
  cells: PublicCell[];
  total_active_cells: number;
  disclaimer: string;
  synthetic: boolean;
}

export interface PublicAlert {
  id: string;
  title: string;
  ward: string;
  time_ago: string;
  severity: 'critical' | 'warning' | 'info';
  description: string;
  icon: string;
}

export interface StatusTimelineStep {
  step: number;
  name: 'received' | 'matched' | 'on_the_way' | 'fulfilled';
  title: string;
  state: 'done' | 'current' | 'pending';
  timestamp?: string | null;
  description: string;
}

export interface AnomalyAlert {
  id: string;
  kind: string;
  title: string;
  reason: string;
  ward_id?: string | null;
  severity: string;
  age_label: string;
  detected_at?: string | null;
  acknowledged: boolean;
}

export interface ReportStatusResponse {
  report_id: string;
  request_id: string;
  public_code?: string | null;
  status: string;
  hero_title: string;
  hero_subtitle: string;
  eta_minutes?: number | null;
  eta_display: string;
  delivery_status: string;
  timeline: StatusTimelineStep[];
  while_you_wait_tips: string[];
  emergency_phone: string;
  synthetic: boolean;
}

