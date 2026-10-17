import { PhotoAnalysis, PhotoInput } from '../models/request.model';
import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
  ScenarioConfig,
  ReportSubmitRequest,
  ReportSubmitResponse,
  ChatTurnResponse,
  UrgencyWeights,
  DedupeDecision,
  RecentReport,
  StoredRequest,
  StoredResource,
  MatchProposal,
  PublicCell,
  PublicCellsResponse,
  PublicAlert,
  AnomalyAlert,
  ReportStatusResponse,
} from '../models/request.model';
import { AuthService } from './auth.service';

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  gemini_enabled: boolean;
  demo_mode: boolean;
}

export interface AiHealthResponse {
  provider: string;
  model: string;
  label: string;
  last_success_at?: string | null;
  cache_hit_rate?: number;
  quota?: {
    daily_cap?: number;
    calls?: number;
    circuit?: string;
    last_success?: boolean;
    last_failure?: string | null;
  };
}

export interface LiveDemoState {
  running: boolean;
  status: string;
  received: number;
  total: number;
  joined: number;
  flagged: number;
  critical: number;
  queue_position: number;
  active_id?: string | null;
  critical_id?: string | null;
  hoax_id?: string | null;
  primary_id?: string | null;
  case_ids?: string[];
  error?: string | null;
}

export interface SitrepResponse {
  brief: string;
  counts: {
    pending: number;
    by_tier: Record<string, number>;
    rescue_open: number;
    rooftop_like: number;
    free_boats: number;
    free_medical: number;
    free_food: number;
    free_shelter: number;
    boat_gap: number;
    gaps: string[];
  };
  drafts: {
    sms_en: string;
    sms_hi: string;
    sms_ml: string;
    whatsapp_en: string;
    whatsapp_hi: string;
    whatsapp_ml: string;
  };
  ai: { provider: string; model?: string | null; fallback_reason?: string | null };
  cached: boolean;
  send: false;
}

export interface ChatTurnPayload {
  session_id?: string;
  message: string;
  scenario_id?: string;
  language?: string;
  location_pin?: { lat: number; lng: number };
}

export interface NoTeamPick { team_id: string; team: string; km?: number | null; eta_min?: number | null; free_in_min?: number; job?: string | null; kind?: string }
export interface NoTeamOptions {
  request_id: string;
  reason: 'all_busy' | 'too_far' | 'too_small' | 'none_of_kind' | 'info_only' | 'no_location' | 'deep_water';
  detail: { busy?: number; km?: number; limit?: number; team?: string; seats?: number; need?: number };
  limit_km: number;
  kind: string | null;
  options: { reserve: NoTeamPick | null; road: NoTeamPick | null; wider: NoTeamPick | null; escalate: { available: boolean } };
}

@Injectable({
  providedIn: 'root',
})
export class ApiClientService {
  private http = inject(HttpClient);
  private authService = inject(AuthService, { optional: true });

  private getAuthHeaders(): { headers?: { [header: string]: string } } {
    const token = this.authService?.getToken();
    if (token) {
      return { headers: { Authorization: `Bearer ${token}` } };
    }
    return {};
  }

  getHealth(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>('/api/health');
  }

  getAiHealth(): Observable<AiHealthResponse> {
    return this.http.get<AiHealthResponse>('/api/health/ai');
  }

  generateSitrep(): Observable<SitrepResponse> {
    return this.http.post<SitrepResponse>('/api/sitrep', {}, this.getAuthHeaders());
  }

  submitSampleReport(kind: 'hindi' | 'voice' | 'photo' | 'duplicate'): Observable<ReportSubmitResponse> {
    return this.http.post<ReportSubmitResponse>('/api/demo/sample-report', { kind });
  }

  startLiveDemo(): Observable<LiveDemoState> {
    return this.http.post<LiveDemoState>('/api/demo/live-run', {}, this.getAuthHeaders());
  }

  getLiveDemo(): Observable<LiveDemoState> {
    return this.http.get<LiveDemoState>('/api/demo/live-run', this.getAuthHeaders());
  }

  submitOwnReport(text: string): Observable<ReportSubmitResponse> {
    return this.http.post<ReportSubmitResponse>('/api/demo/own-report', { text }, this.getAuthHeaders());
  }

  getScenarios(): Observable<ScenarioConfig[]> {
    return this.http.get<ScenarioConfig[]>('/api/scenarios');
  }

  getScenario(id: string): Observable<ScenarioConfig> {
    return this.http.get<ScenarioConfig>(`/api/scenarios/${id}`);
  }

  sendChatTurn(payload: ChatTurnPayload): Observable<ChatTurnResponse> {
    return this.http.post<ChatTurnResponse>('/api/intake/chat', payload);
  }

  submitReport(payload: ReportSubmitRequest): Observable<ReportSubmitResponse> {
    return this.http.post<ReportSubmitResponse>('/api/reports', payload);
  }

  getUrgencyWeights(): Observable<UrgencyWeights> {
    return this.http.get<UrgencyWeights>('/api/config/weights', this.getAuthHeaders());
  }

  updateUrgencyWeights(weights: UrgencyWeights): Observable<UrgencyWeights> {
    return this.http.put<UrgencyWeights>('/api/config/weights', weights, this.getAuthHeaders());
  }

  mergeRequests(primaryId: string, secondaryId: string, evidence: string[] = []): Observable<any> {
    return this.http.post<any>(
      `/api/requests/${primaryId}/merge`,
      {
        secondary_request_id: secondaryId,
        evidence,
      },
      this.getAuthHeaders()
    );
  }

  keepSeparate(requestId: string): Observable<any> {
    return this.http.post<any>(`/api/requests/${requestId}/keep-separate`, {}, this.getAuthHeaders());
  }

  splitCluster(requestId: string): Observable<any> {
    return this.http.post<any>(`/api/requests/${requestId}/split`, {}, this.getAuthHeaders());
  }

  getCluster(clusterId: string): Observable<any> {
    return this.http.get<any>(`/api/clusters/${clusterId}`, this.getAuthHeaders());
  }

  getMerge(requestId: string): Observable<any> {
    return this.http.get<any>(`/api/cases/${requestId}/merge`, this.getAuthHeaders());
  }

  analysePhoto(payload: PhotoInput): Observable<PhotoAnalysis> {
    return this.http.post<PhotoAnalysis>('/api/intake/photo', payload);
  }

  simulateSurge(): Observable<{ run_id: string; running: boolean; submitted: number; failed: number; total: number }> {
    return this.http.post<{ run_id: string; running: boolean; submitted: number; failed: number; total: number }>('/api/demo/simulate-surge', {}, this.getAuthHeaders());
  }

  getSurgeState(): Observable<{ run_id: string; running: boolean; submitted: number; failed: number; total: number }> {
    return this.http.get<{ run_id: string; running: boolean; submitted: number; failed: number; total: number }>('/api/demo/surge', this.getAuthHeaders());
  }

  loadScenarioDemo(packId: string): Observable<{ pack_id: string; loaded: boolean }> {
    return this.http.post<{ pack_id: string; loaded: boolean }>(`/api/demo/scenario/${encodeURIComponent(packId)}`, {}, this.getAuthHeaders());
  }

  /** Reload the two-case demo. The API allows it in demo mode or for the demo coordinator. */
  resetDemo(): Observable<any> {
    return this.http.post<any>('/api/demo/reset', {}, this.getAuthHeaders());
  }

  /** Load every synthetic flood case. Reset returns to the two-case demo. */
  loadFullScenario(): Observable<any> {
    return this.http.post<any>('/api/demo/full', {}, this.getAuthHeaders());
  }

  /** Ask the desk. Read-only search over cases; Gemini picks the filters, rules if it cannot. */
  askDesk(question: string, lang?: string): Observable<any> {
    return this.http.post<any>('/api/desk/ask', { question, lang }, this.getAuthHeaders());
  }

  getAssistProposals(): Observable<any> {
    return this.http.get<any>('/api/assist/proposals', this.getAuthHeaders());
  }

  planAssist(): Observable<any> {
    return this.http.post<any>('/api/assist/plan', {}, this.getAuthHeaders());
  }

  verifyCoordinatorSession(): Observable<any> {
    return this.http.get<any>('/api/coordinator/verify', this.getAuthHeaders());
  }

  getMapsConfig(): Observable<{ enabled: boolean; apiKey: string | null }> {
    return this.http.get<{ enabled: boolean; apiKey: string | null }>('/api/config/maps');
  }

  /** Citizen reports from the last 15 minutes, newest first. */
  getRecentReports(minutes = 15): Observable<RecentReport[]> {
    return this.http.get<RecentReport[]>(`/api/recent-reports?minutes=${minutes}`, this.getAuthHeaders());
  }

  getRequests(sort = 'urgency', packId?: string, updatedSince?: string): Observable<StoredRequest[]> {
    const pack = packId ? `&pack_id=${encodeURIComponent(packId)}` : '';
    const since = updatedSince ? `&updated_since=${encodeURIComponent(updatedSince)}` : '';
    return this.http.get<StoredRequest[]>(`/api/requests?sort=${sort}${pack}${since}`, this.getAuthHeaders());
  }

  getRequest(id: string): Observable<StoredRequest> {
    return this.http.get<StoredRequest>(`/api/requests/${id}`, this.getAuthHeaders());
  }

  getRequestMatches(id: string, topN = 5): Observable<MatchProposal[]> {
    return this.http.get<MatchProposal[]>(`/api/requests/${id}/matches?top_n=${topN}`, this.getAuthHeaders());
  }

  undoMatch(matchId: string): Observable<any> {

    return this.http.post<any>(`/api/matches/${matchId}/undo`, {}, this.getAuthHeaders());

  }


  approveMatch(id: string, allowOvercommit = false, confirmTake = false): Observable<any> {
    return this.http.post<any>(
      `/api/matches/${id}/approve`,
      { allow_overcommit: allowOvercommit, confirm_take: confirmTake },
      this.getAuthHeaders()
    );
  }

  markArrived(id: string): Observable<StoredRequest> {
    return this.http.post<StoredRequest>(`/api/requests/${id}/arrived`, {}, this.getAuthHeaders());
  }

  getNoTeam(id: string): Observable<NoTeamOptions> {
    return this.http.get<NoTeamOptions>(`/api/requests/${id}/no-team`, this.getAuthHeaders());
  }

  chooseNoTeam(id: string, option: string): Observable<{ option: string; sent: boolean }> {
    return this.http.post<{ option: string; sent: boolean }>(`/api/requests/${id}/no-team`, { option }, this.getAuthHeaders());
  }

  dismissHoax(id: string): Observable<StoredRequest> {
    return this.http.post<StoredRequest>(`/api/requests/${id}/dismiss-hoax`, {}, this.getAuthHeaders());
  }

  completeRequest(id: string): Observable<StoredRequest> {
    return this.http.post<StoredRequest>(`/api/requests/${id}/complete`, {}, this.getAuthHeaders());
  }

  rejectMatch(id: string, reason: string): Observable<any> {
    return this.http.post<any>(
      `/api/matches/${id}/reject`,
      { reason },
      this.getAuthHeaders()
    );
  }

  updateResourceLocation(id: string, lat: number, lng: number): Observable<StoredResource> {
    return this.http.post<StoredResource>(`/api/resources/${id}/location`, { lat, lng }, this.getAuthHeaders());
  }

  getTeam(id: string): Observable<StoredResource> {
    return this.http.get<StoredResource>(`/api/team/${id}`);
  }

  confirmTeam(id: string, action: 'at_scene' | 'done' | 'available'): Observable<StoredResource> {
    return this.http.post<StoredResource>(`/api/team/${id}`, { action });
  }

  shareTeamLocation(id: string, lat: number, lng: number): Observable<StoredResource> {
    return this.http.post<StoredResource>(`/api/team/${id}/location`, { lat, lng });
  }

  getResources(kind?: string): Observable<StoredResource[]> {
    const url = kind ? `/api/resources?kind=${kind}` : '/api/resources';
    return this.http.get<StoredResource[]>(url, this.getAuthHeaders());
  }

  getPublicCells(bbox?: string): Observable<PublicCellsResponse> {
    const url = bbox ? `/api/public/cells?bbox=${bbox}` : '/api/public/cells';
    return this.http.get<PublicCellsResponse>(url);
  }

  getPublicAlerts(): Observable<PublicAlert[]> {
    return this.http.get<PublicAlert[]>('/api/public/alerts');
  }

  getReportStatus(reportId: string, token?: string): Observable<ReportStatusResponse> {
    const url = token
      ? `/api/reports/${reportId}/status?token=${token}`
      : `/api/reports/${reportId}/status`;
    return this.http.get<ReportStatusResponse>(url);
  }

  getAlerts(): Observable<AnomalyAlert[]> {
    return this.http.get<AnomalyAlert[]>('/api/alerts', this.getAuthHeaders());
  }

  getBenchmark(): Observable<Record<string, unknown>> {
    return this.http.get<Record<string, unknown>>('/api/benchmark/latest', this.getAuthHeaders());
  }

  acknowledgeAlert(id: string): Observable<AnomalyAlert> {
    return this.http.post<AnomalyAlert>(`/api/alerts/${id}/acknowledge`, {}, this.getAuthHeaders());
  }
}
