import { Injectable, inject, signal } from '@angular/core';
import { ApiClientService } from '@rd/shared';
import { Subscription } from 'rxjs';

/** How long the first health call may sit before we tell the user the server is waking. */
export const COLD_START_REVEAL_MS = 1500;
/** Give one Cloud Run cold start a chance to finish before the next try. */
export const COLD_START_ATTEMPT_MS = 10_000;
export const COLD_START_MAX_ATTEMPTS = 4;
/** Wait after attempt 1, 2, and 3. */
export const COLD_START_BACKOFF_MS = [1000, 2000, 4000];

export type ColdStartPhase = 'idle' | 'waking' | 'failed';

/**
 * Pings `/api/health` as soon as the app boots so a scaled-to-zero Cloud Run
 * instance can start before the user clicks. The banner stays hidden unless
 * that first wake is still pending after ~1.5s.
 */
@Injectable({ providedIn: 'root' })
export class ColdStartService {
  private readonly api = inject(ApiClientService);
  private readonly phaseState = signal<ColdStartPhase>('idle');
  readonly phase = this.phaseState.asReadonly();

  private ready = false;
  private running = false;
  private readonly subs: Subscription[] = [];
  private revealTimer: ReturnType<typeof setTimeout> | null = null;
  private attemptTimer: ReturnType<typeof setTimeout> | null = null;
  private backoffTimer: ReturnType<typeof setTimeout> | null = null;

  /** Fire-and-forget. Safe to call more than once. */
  start(): void {
    if (this.running || this.ready) return;
    this.running = true;
    this.revealTimer = setTimeout(() => {
      if (!this.ready && this.phaseState() !== 'failed') this.phaseState.set('waking');
    }, COLD_START_REVEAL_MS);
    this.ping(1);
  }

  /** User asked to try the wake again after the retries were used up. */
  retry(): void {
    this.clearTimers();
    this.stopSubs();
    this.ready = false;
    this.running = true;
    this.phaseState.set('waking');
    this.ping(1);
  }

  private ping(attempt: number): void {
    if (this.attemptTimer) clearTimeout(this.attemptTimer);
    let closed = false;
    this.attemptTimer = setTimeout(() => {
      if (closed || this.ready) return;
      closed = true;
      this.attemptTimer = null;
      this.failAttempt(attempt);
    }, COLD_START_ATTEMPT_MS);

    // Keep the request open across the timeout. A late 200 still means the instance is up.
    const sub = this.api.getHealth().subscribe({
      next: () => this.succeed(),
      error: () => {
        if (closed || this.ready) return;
        closed = true;
        if (this.attemptTimer) clearTimeout(this.attemptTimer);
        this.attemptTimer = null;
        this.failAttempt(attempt);
      },
    });
    this.subs.push(sub);
  }

  private failAttempt(attempt: number): void {
    if (this.ready) return;
    if (attempt >= COLD_START_MAX_ATTEMPTS) {
      this.clearTimers();
      this.running = false;
      this.phaseState.set('failed');
      return;
    }
    const wait = COLD_START_BACKOFF_MS[attempt - 1] ?? COLD_START_BACKOFF_MS[COLD_START_BACKOFF_MS.length - 1];
    this.backoffTimer = setTimeout(() => this.ping(attempt + 1), wait);
  }

  private succeed(): void {
    if (this.ready) return;
    this.ready = true;
    this.running = false;
    this.clearTimers();
    this.stopSubs();
    this.phaseState.set('idle');
  }

  private stopSubs(): void {
    for (const sub of this.subs) sub.unsubscribe();
    this.subs.length = 0;
  }

  private clearTimers(): void {
    if (this.revealTimer) clearTimeout(this.revealTimer);
    if (this.attemptTimer) clearTimeout(this.attemptTimer);
    if (this.backoffTimer) clearTimeout(this.backoffTimer);
    this.revealTimer = null;
    this.attemptTimer = null;
    this.backoffTimer = null;
  }
}
