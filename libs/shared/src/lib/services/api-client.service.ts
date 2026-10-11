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
} from '../models/request.model';

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
    return this.http.get<UrgencyWeights>('/api/config/weights');
  }

  updateUrgencyWeights(weights: UrgencyWeights): Observable<UrgencyWeights> {
    return this.http.put<UrgencyWeights>('/api/config/weights', weights);
  }

  mergeRequests(primaryId: string, secondaryId: string, evidence: string[] = []): Observable<any> {
    return this.http.post<any>(`/api/requests/${primaryId}/merge`, {
      secondary_request_id: secondaryId,
      evidence,
    });
  }

  splitCluster(requestId: string): Observable<any> {
    return this.http.post<any>(`/api/requests/${requestId}/split`, {});
  }

  getCluster(clusterId: string): Observable<any> {
    return this.http.get<any>(`/api/clusters/${clusterId}`);
  }
}
