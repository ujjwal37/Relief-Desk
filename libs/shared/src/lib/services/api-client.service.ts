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

export interface ChatTurnPayload {
  session_id?: string;
  message: string;
  scenario_id?: string;
  language?: string;
  location_pin?: { lat: number; lng: number };
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
    return this.http.get<HealthResponse>('/healthz');
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

  splitCluster(requestId: string): Observable<any> {
    return this.http.post<any>(`/api/requests/${requestId}/split`, {}, this.getAuthHeaders());
  }

  getCluster(clusterId: string): Observable<any> {
    return this.http.get<any>(`/api/clusters/${clusterId}`, this.getAuthHeaders());
  }

  verifyCoordinatorSession(): Observable<any> {
    return this.http.get<any>('/api/coordinator/verify', this.getAuthHeaders());
  }

  getMapsConfig(): Observable<{ enabled: boolean; apiKey: string | null }> {
    return this.http.get<{ enabled: boolean; apiKey: string | null }>('/api/config/maps');
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

  approveMatch(id: string, allowOvercommit = false): Observable<any> {
    return this.http.post<any>(
      `/api/matches/${id}/approve`,
      { allow_overcommit: allowOvercommit },
      this.getAuthHeaders()
    );
  }

  markArrived(id: string): Observable<StoredRequest> {
    return this.http.post<StoredRequest>(`/api/requests/${id}/arrived`, {}, this.getAuthHeaders());
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
