import { Injectable, OnDestroy, inject, signal } from '@angular/core';
import { AuthService } from '@rd/shared';
import { Subscription } from 'rxjs';
import { Subject } from 'rxjs';
import { DeskStore } from './desk-store';

export type LiveState = 'live' | 'reconnecting' | 'offline';
export type DeskKind = 'cases' | 'teams' | 'alerts' | 'recent' | 'all';

export interface LiveEvent {
  type: string;
  id?: string;
  request_id?: string | null;
  request_ids?: string[];
  run_id?: string;
  running?: boolean;
  submitted?: number;
  failed?: number;
  total?: number;
  agent?: string;
  status?: string;
  summary?: string;
  similarity?: number;
  match_id?: string;
  tier?: string;
  score?: number;
  team?: string;
  received?: number;
  joined?: number;
  flagged?: number;
  critical?: number;
  queue_position?: number;
  critical_id?: string | null;
  active_id?: string | null;
}

const NAMES = ['case.created', 'case.merged', 'case.updated', 'dispatch.created', 'team.updated', 'alert.created', 'heartbeat', 'demo.surge', 'demo.progress', 'pipeline.step'];

/** 1s, 2s, 4s… capped at 15s. */
export function backoffMs(attempt: number): number {
  return Math.min(15000, 1000 * 2 ** Math.max(0, attempt));
}

/** Which desk lists an event should refresh. Heartbeats refresh nothing. */
export function kindsFor(type: string): DeskKind[] {
  if (type === 'case.created' || type === 'case.merged' || type === 'case.updated') {
    return ['cases', 'recent', 'alerts'];
  }
  if (type === 'dispatch.created') return ['cases', 'recent', 'alerts', 'teams'];
  if (type === 'team.updated') return ['teams'];
  if (type === 'alert.created') return ['alerts'];
  if (type === 'pipeline.step') return [];
  return [];
}

/**
 * One EventSource per page. The desk uses the coordinator token.
 * The status page uses its report id and status token, and only hears that case.
 */
/** Cloud Run origin for the live stream. Firebase Hosting buffers rewritten responses, so a
 * stream through it never reaches the browser. Override with window.RD_STREAM_BASE. */
export const CLOUD_RUN_STREAM_BASE = 'https://relief-desk-api-495181973767.asia-south1.run.app';

export function streamBase(): string {
  if (typeof window === 'undefined') return '';
  const override = (window as unknown as { RD_STREAM_BASE?: string }).RD_STREAM_BASE;
  if (typeof override === 'string') return override.replace(/\/$/, '');
  const host = window.location?.hostname || '';
  return /\.(web\.app|firebaseapp\.com)$/.test(host) ? CLOUD_RUN_STREAM_BASE : '';
}

@Injectable({ providedIn: 'root' })
export class LiveEventsService implements OnDestroy {
  private readonly auth = inject(AuthService);
  private readonly desk = inject(DeskStore);
  readonly state = signal<LiveState>('reconnecting');
  readonly kinds = new Subject<DeskKind>();
  private source: EventSource | null = null;
  private url = '';
  private attempt = 0;
  private retry: ReturnType<typeof setTimeout> | null = null;
  private fallback: ReturnType<typeof setInterval> | null = null;
  private watchdog: ReturnType<typeof setInterval> | null = null;
  private lastBeat = 0;
  private stopped = false;
  private mode: 'desk' | 'report' | '' = '';
  private listeners = new Set<(event: LiveEvent) => void>();
  private deskSub?: Subscription;

  constructor() {
    this.deskSub = this.kinds.subscribe((kind) => this.desk.apply(kind));
  }

  /** Coordinator shell. Falls back to a 5s refresh when the stream is down. */
  connectDesk(): void {
    const token = this.auth.getToken();
    if (!token) {
      this.state.set('offline');
      this.mode = 'desk';
      this.armFallback();
      return;
    }
    this.mode = 'desk';
    this.open(`${streamBase()}/api/events?token=${encodeURIComponent(token)}`);
  }

  /** Reporter status. The server only forwards events for this case. */
  connectReport(reportId: string, statusToken: string): void {
    if (!reportId || !statusToken) return;
    this.mode = 'report';
    this.open(`${streamBase()}/api/events?report_id=${encodeURIComponent(reportId)}&status_token=${encodeURIComponent(statusToken)}`);
  }

  onEvent(listener: (event: LiveEvent) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Used by tests and by the stream listener. */
  ingest(event: LiveEvent): void {
    if (event.type === 'heartbeat') {
      this.lastBeat = Date.now();
      return;
    }
    this.lastBeat = Date.now();
    if (event.type === 'case.merged') this.desk.noteMerge(event.request_ids || []);
    for (const listener of this.listeners) listener(event);
    for (const kind of kindsFor(event.type)) this.kinds.next(kind);
  }

  /** Close the stream. The desk store keeps listening for the next connect. */
  stop(): void {
    this.stopped = true;
    this.closeSource();
    this.clearTimers();
  }

  ngOnDestroy(): void {
    this.stop();
    this.deskSub?.unsubscribe();
  }

  private open(url: string): void {
    this.stopped = false;
    this.url = url;
    this.clearTimers();
    this.armFallback();
    this.armWatchdog();
    this.connect();
  }

  private connect(): void {
    this.closeSource();
    if (this.stopped || !this.url || typeof EventSource === 'undefined') {
      this.state.set('offline');
      return;
    }
    this.state.set(this.attempt > 2 ? 'offline' : 'reconnecting');
    const source = new EventSource(this.url);
    this.source = source;
    source.onopen = () => {
      this.attempt = 0;
      this.lastBeat = Date.now();
      this.state.set('live');
    };
    source.onerror = () => this.fail();
    for (const name of NAMES) {
      source.addEventListener(name, (message) => this.onMessage(name, message as MessageEvent));
    }
  }

  private onMessage(name: string, message: MessageEvent): void {
    this.lastBeat = Date.now();
    if (name === 'heartbeat') return;
    let data: LiveEvent = { type: name };
    try {
      const parsed = JSON.parse(message.data || '{}') as LiveEvent;
      data = { ...parsed, type: parsed.type || name };
    } catch {
      data = { type: name };
    }
    this.ingest(data);
  }

  private fail(): void {
    this.closeSource();
    if (this.stopped) return;
    this.state.set(this.attempt > 2 ? 'offline' : 'reconnecting');
    const wait = backoffMs(this.attempt);
    this.attempt += 1;
    if (this.retry) clearTimeout(this.retry);
    this.retry = setTimeout(() => this.connect(), wait);
  }

  private armFallback(): void {
    if (this.fallback) return;
    this.fallback = setInterval(() => {
      if (this.stopped || this.mode !== 'desk' || this.state() === 'live') return;
      this.kinds.next('all');
    }, 5000);
  }

  private armWatchdog(): void {
    if (this.watchdog) return;
    this.watchdog = setInterval(() => {
      if (this.stopped || this.state() !== 'live') return;
      if (this.lastBeat && Date.now() - this.lastBeat > 20000) this.fail();
    }, 5000);
  }

  private closeSource(): void {
    this.source?.close();
    this.source = null;
  }

  private clearTimers(): void {
    if (this.retry) clearTimeout(this.retry);
    if (this.fallback) clearInterval(this.fallback);
    if (this.watchdog) clearInterval(this.watchdog);
    this.retry = null;
    this.fallback = null;
    this.watchdog = null;
  }
}
