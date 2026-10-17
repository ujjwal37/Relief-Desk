import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { timeout } from 'rxjs';
import { ApiClientService, LanguageService, RdTranslatePipe, SitrepResponse, StoredRequest, urgencyBand } from '@rd/shared';
import { MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';
import { teamTone } from '../../../core/maps/map-markers';
import { DeskStore } from '../../../core/desk-store';

const SENT = new Set(['approved', 'dispatched', 'in_progress']);
const DONE = new Set(['completed', 'resolved', 'closed']);
const DISMISSED = new Set(['dismissed_hoax']);
const BRIEF_MIN_GAP_MS = 3 * 60 * 1000;

interface Area { ward: string; label: string; critical: number; urgent: number; waiting: number; freeTeams: number; }

/** Situation: where it is worst, what is waiting, which teams are free. Every number comes from the desk data. */
/** Areas are grouped and named by ward, never by a case title. */
const WARD_NAME: Record<string, string> = { ward_1: 'Kainakary', ward_2: 'Champakulam', ward_3: 'Nedumudi' };

@Component({
  selector: 'app-coordinator-situation',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RdTranslatePipe, MapProviderComponent],
  template: `
    <div class="sit">
      <header class="sit-head">
        <div>
          <h1>{{ 'sit.title' | rdTranslate }}</h1>
          <p class="lead" data-testid="sit-ratio">{{ 'sit.ratio' | rdTranslate:{ r: stats().reports, c: stats().cases } }}</p>
        </div>
        <button type="button" class="primary" data-testid="sit-open-command" (click)="openArea(null)">{{ 'sit.openCommand' | rdTranslate }}</button>
      </header>

      @if (!desk.casesReady()) {
        <div class="tiles">@for (i of [1,2,3,4,5,6]; track i) { <div class="tile skel"></div> }</div>
      } @else {
        <div class="tiles" data-testid="sit-tiles">
          <div class="tile"><b>{{ stats().waiting }}</b><span>{{ 'batch.waiting' | rdTranslate }}</span></div>
          <div class="tile"><b>{{ stats().dispatched }}</b><span>{{ 'batch.dispatched' | rdTranslate }}</span></div>
          <div class="tile"><b>{{ stats().completed }}</b><span>{{ 'sit.completed' | rdTranslate }}</span></div>
          <div class="tile"><b>{{ stats().merged }}</b><span>{{ 'sit.merged' | rdTranslate }}</span></div>
          <div class="tile"><b>{{ stats().hoax }}</b><span>{{ 'sit.hoax' | rdTranslate }}</span></div>
          <div class="tile"><b>{{ stats().perMin }}</b><span>{{ 'sit.perMin' | rdTranslate }}</span></div>
        </div>
      }

      <div class="grid">
        <section class="panel map" [attr.aria-label]="'ui.map' | rdTranslate">
          <rd-map-provider [pins]="pins()" [legs]="[]" [center]="{ lat: 10.3, lng: 76.33 }" [cluster]="true" [fitAll]="true" (pinSelect)="openCase($event)"></rd-map-provider>
        </section>
        <div class="side">
          <section class="panel brief" data-testid="sit-brief">
            <div class="brief-head">
              <h2>{{ 'sit.brief' | rdTranslate }}</h2>
              @if (brief(); as b) { <span class="badge" [class.gemini]="briefSource() === 'gemini'">{{ briefBadge() }}</span> }
              <button type="button" class="ghost" [disabled]="briefBusy() || !canRefresh()" (click)="loadBrief(true)">{{ 'sit.refresh' | rdTranslate }}</button>
            </div>
            @if (briefBusy() && !brief()) { <div class="brief-skel" role="status" [attr.aria-label]="'sit.briefLoading' | rdTranslate"><i></i><i></i><i></i></div> }
            @else if (brief(); as b) { <p class="brief-text">{{ b.brief }}</p> }
            @else if (briefError()) { <p class="empty" data-testid="brief-unavailable">{{ 'sit.briefUnavailable' | rdTranslate }} · <button type="button" class="ghost" (click)="loadBrief(false)">{{ 'bench.retry' | rdTranslate }}</button></p> }
          </section>
          <section class="panel">
            <h2>{{ 'sit.topAreas' | rdTranslate }}</h2>
            @if (areas().length === 0) {
              <p class="empty">{{ 'sit.allClear' | rdTranslate }}</p>
            } @else {
              <ol class="areas" data-testid="sit-areas">
                @for (a of areas(); track a.ward; let i = $index) {
                  <li><button type="button" (click)="openArea(a.ward)">
                    <span class="rank">{{ i + 1 }}</span>
                    <span class="name">{{ a.label }}</span>
                    <span class="crit">▲ {{ a.critical }}</span>
                    <span class="meta">{{ 'sit.areaMeta' | rdTranslate:{ w: a.waiting, t: a.freeTeams } }}</span>
                  </button></li>
                }
              </ol>
            }
          </section>
          <section class="panel">
            <h2>{{ 'sit.teams' | rdTranslate }}</h2>
            <ul class="kinds">
              @for (k of teamKinds(); track k.kind) {
                <li><span>{{ ('coord.kind.' + k.kind) | rdTranslate }}</span><span><i class="dot free"></i>{{ k.free }} {{ 'sit.free' | rdTranslate }} · <i class="dot busy"></i>{{ k.busy }} {{ 'sit.busy' | rdTranslate }}@if (k.stale) { · <i class="dot stale"></i>{{ k.stale }} {{ 'sit.notUpdated' | rdTranslate }} }</span></li>
              }
            </ul>
          </section>
        </div>
      </div>
    </div>
  `,
  styles: [`
    :host { display:block; height:100%; overflow:auto; background:var(--bg); }
    .sit { padding: 20px 24px; display:flex; flex-direction:column; gap:16px; max-width:1600px; margin:0 auto; }
    .sit-head { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; }
    h1 { margin:0; font-size:24px; font-weight:600; color:var(--text); }
    h2 { margin:0 0 10px; font-size:14px; font-weight:600; color:var(--text); }
    .lead { margin:4px 0 0; color:var(--text-2); font-size:14px; font-variant-numeric:tabular-nums; }
    .dot.stale { background: var(--muted, #8a8a8a); }
    .primary { border:0; border-radius:var(--r2); padding:10px 18px; font:inherit; font-weight:600; background:var(--brand); color:var(--on-brand); cursor:pointer; }
    .primary:hover { filter:brightness(1.08); }
    .ghost { margin-left:auto; border:1px solid var(--border-2, var(--border)); background:var(--card); color:var(--text); border-radius:var(--r1); padding:4px 10px; font:inherit; font-size:12px; cursor:pointer; }
    .ghost:hover:not(:disabled) { background:var(--brand-tint); }
    button:focus-visible { outline:2px solid var(--focus); outline-offset:2px; }
    button:disabled { opacity:.55; cursor:not-allowed; }
    .panel.brief { border-color:var(--border-2); background:var(--card); }
    .panel.brief:has(.badge.gemini) { border-color:var(--gemini); background:color-mix(in srgb, var(--gemini) 5%, var(--card)); }
    .panel.brief .brief-text { font-size:15px; line-height:1.55; color:var(--text); }
    .tiles { display:grid; grid-template-columns:repeat(6, minmax(0,1fr)); gap:12px; }
    .tile { background:var(--card); border:1px solid var(--border); border-radius:var(--r3, 12px); padding:12px 14px; display:flex; flex-direction:column; gap:2px; min-height:64px; }
    .tile b { font-size:24px; font-weight:600; color:var(--text); font-variant-numeric:tabular-nums; }
    .tile span { font-size:12px; color:var(--text-2); }
    .skel { background:var(--surface-2); animation:pulse 1.2s ease-in-out infinite; }
    @keyframes pulse { 50% { opacity:.5; } }
    @media (prefers-reduced-motion: reduce) { .skel { animation:none; } }
    .grid { display:grid; grid-template-columns:minmax(0,1fr) 400px; gap:16px; min-height:520px; }
    .panel { background:var(--card); border:1px solid var(--border); border-radius:var(--r3, 12px); padding:14px 16px; }
    .brief-skel { display:flex; flex-direction:column; gap:8px; padding:4px 0; }
    .brief-skel i { display:block; height:12px; border-radius:6px; background:linear-gradient(90deg, var(--surface-2) 25%, var(--border) 50%, var(--surface-2) 75%); background-size:200% 100%; animation:bsk 1.6s ease-in-out infinite; }
    .brief-skel i:nth-child(2) { width:85%; } .brief-skel i:nth-child(3) { width:60%; }
    @keyframes bsk { to { background-position:-200% 0; } }
    @media (prefers-reduced-motion: reduce) { .brief-skel i { animation:none; } }
    .map { padding:0; overflow:hidden; min-height:520px; position:relative; }
    .map rd-map-provider { display:block; width:100%; height:100%; min-height:520px; }
    .side { display:flex; flex-direction:column; gap:16px; }
    .areas { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:6px; }
    .areas button { width:100%; display:grid; grid-template-columns:24px 1fr auto; grid-template-rows:auto auto; column-gap:8px; text-align:left; border:1px solid var(--border); background:var(--surface); color:var(--text); border-radius:var(--r2); padding:8px 10px; font:inherit; cursor:pointer; }
    .areas button:hover { background:var(--brand-tint); border-color:var(--border-2, var(--border)); }
    .rank { grid-row:span 2; font-weight:600; color:var(--text-2); font-variant-numeric:tabular-nums; }
    .name { font-weight:600; font-size:14px; }
    .crit { color:var(--sev-crit); font-weight:600; font-size:13px; }
    .meta { grid-column:2 / span 2; font-size:12px; color:var(--text-2); }
    .kinds { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:6px; font-size:13px; }
    .kinds li { display:flex; justify-content:space-between; color:var(--text); }
    .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin:0 4px 0 6px; }
    .dot.free { background:var(--ok, var(--green)); } .dot.busy { background:var(--amber); }
    .brief-head { display:flex; align-items:center; gap:8px; margin-bottom:6px; }
    .brief-head h2 { margin:0; }
    .badge { font-size:11px; padding:2px 8px; border-radius:999px; background:var(--surface-2); color:var(--text-2); }
    .badge.gemini { background:var(--gemini-t); color:var(--gemini); }
    .brief-text { margin:0; font-size:14px; line-height:1.55; color:var(--text); white-space:pre-line; }
    .empty { margin:0; font-size:13px; color:var(--text-2); }
    @media (max-width: 1280px) { .grid { grid-template-columns:minmax(0,1fr) 340px; } .tiles { grid-template-columns:repeat(3, minmax(0,1fr)); } }
  `],
})
export class CoordinatorSituationComponent implements OnInit {
  readonly desk = inject(DeskStore);
  private readonly api = inject(ApiClientService);
  private readonly router = inject(Router);
  private readonly lang = inject(LanguageService);

  readonly brief = signal<SitrepResponse | null>(null);
  readonly briefBusy = signal(false);
  readonly briefError = signal(false);
  private lastBriefAt = 0;
  private rechecked = false;
  private readonly now = signal(Date.now());

  private open(r: StoredRequest): boolean {
    const s = String(r.status || '');
    return !SENT.has(s) && !DONE.has(s) && !DISMISSED.has(s) && !r.merged_into;
  }

  readonly stats = computed(() => {
    const rows = this.desk.requests().filter((r) => !r.merged_into);
    const reports = rows.reduce((n, r) => n + (r.merged_count || 1), 0);
    const cutoff = this.now() - 10 * 60 * 1000;
    const recent = rows.reduce((n, r) => n + (r.created_at && Date.parse(r.created_at) >= cutoff ? 1 : 0), 0);
    return {
      reports,
      cases: rows.length,
      perMin: Math.round((recent / 10) * 10) / 10,
      waiting: rows.filter((r) => this.open(r)).length,
      dispatched: rows.filter((r) => SENT.has(String(r.status))).length,
      completed: rows.filter((r) => DONE.has(String(r.status))).length,
      merged: reports - rows.length,
      hoax: rows.filter((r) => (r.flags || []).some((f) => f === 'hoax' || f === 'likely_hoax')).length,
    };
  });

  readonly pins = computed<MapPin[]>(() =>
    this.desk.requests()
      .filter((r) => this.open(r) && r.lat != null && r.lng != null)
      .filter((r) => ['critical', 'high'].includes(urgencyBand(r.urgency_score)))
      .map((r) => ({ id: r.id, lat: r.lat as number, lng: r.lng as number, title: r.place_text || r.id, marker: 'case' as const, tone: urgencyBand(r.urgency_score) })),
  );

  readonly areas = computed<Area[]>(() => {
    const map = new Map<string, Area & { names: Map<string, number> }>();
    for (const r of this.desk.requests()) {
      if (!this.open(r) || !r.ward_id) continue;
      const a = map.get(r.ward_id) || { ward: r.ward_id, label: '', critical: 0, urgent: 0, waiting: 0, freeTeams: 0, names: new Map() };
      const band = urgencyBand(r.urgency_score);
      if (band === 'critical') a.critical++;
      if (band === 'high') a.urgent++;
      a.waiting++;
      const place = (r.place_text || '').split(/[,.]/)[0].trim().split(/\s+/).slice(0, 4).join(' ');
      if (place) a.names.set(place, (a.names.get(place) || 0) + 1);
      map.set(r.ward_id, a);
    }
    const teams = this.desk.resources();
    const out = [...map.values()].map((a) => {
      const top = [...a.names.entries()].sort((x, y) => y[1] - x[1])[0]?.[0];
      const free = teams.filter((t) => t.ward_id === a.ward && teamTone(t) === 'free').length;
      return { ward: a.ward, label: WARD_NAME[a.ward] || top || a.ward.replace(/^ward_?/i, 'Ward '), critical: a.critical, urgent: a.urgent, waiting: a.waiting, freeTeams: free };
    });
    return out.filter((a) => a.critical + a.urgent > 0).sort((x, y) => y.critical - x.critical || y.urgent - x.urgent || y.waiting - x.waiting).slice(0, 5);
  });

  readonly teamKinds = computed(() => {
    // Same buckets as the Teams page (teamTone): free, busy, not updated.
    const by = new Map<string, { kind: string; free: number; busy: number; stale: number }>();
    for (const t of this.desk.resources()) {
      const k = String(t.kind);
      const row = by.get(k) || { kind: k, free: 0, busy: 0, stale: 0 };
      const tone = teamTone(t);
      if (tone === 'free') row.free++; else if (tone === 'busy') row.busy++; else row.stale++;
      by.set(k, row);
    }
    return [...by.values()];
  });

  briefSource(): string {
    const p = this.brief()?.ai?.provider;
    if (p === 'gemini') return 'gemini';
    if (p === 'cache') return 'recorded';
    if (p === 'antigravity-local') return 'local';
    return 'rules';
  }
  briefBadge(): string {
    this.lang.currentLang();
    return this.lang.translate('sit.src.' + this.briefSource());
  }
  canRefresh(): boolean { return this.now() - this.lastBriefAt >= BRIEF_MIN_GAP_MS; }

  ngOnInit(): void {
    this.desk.refreshCases();
    this.desk.refreshTeams();
    this.loadBrief(false);
    const tick = setInterval(() => this.now.set(Date.now()), 15000);
    window.addEventListener('beforeunload', () => clearInterval(tick), { once: true });
  }

  loadBrief(force: boolean): void {
    if (this.briefBusy() || (force && !this.canRefresh())) return;
    this.briefBusy.set(true);
    this.briefError.set(false);
    this.api.generateSitrep().pipe(timeout(20000)).subscribe({
      next: (res) => {
        this.brief.set(res); this.lastBriefAt = Date.now(); this.now.set(Date.now()); this.briefBusy.set(false);
        // Rules summary shown now; the AI draft is being written. Pick it up once, without a click.
        if (res.ai?.fallback_reason === 'sitrep_warming' && !this.rechecked) { this.rechecked = true; setTimeout(() => this.loadBrief(false), 25000); }
      },
      error: () => { this.briefError.set(true); this.briefBusy.set(false); },
    });
  }

  openArea(ward: string | null): void {
    void this.router.navigate(['/coordinator/command'], { queryParams: ward ? { area: ward } : {} });
  }
  openCase(id: string): void {
    void this.router.navigate(['/coordinator/command'], { queryParams: { case: id } });
  }
}
