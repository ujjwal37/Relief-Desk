import { Injectable, inject, signal } from '@angular/core';
import { ApiClientService, ScenarioConfig } from '@rd/shared';

@Injectable({ providedIn: 'root' })
export class ScenarioService {
  private api = inject(ApiClientService);
  private started = false;

  readonly scenarios = signal<ScenarioConfig[]>([]);
  readonly activeId = signal('flood');

  ensureLoaded(): void {
    if (this.started) {
      return;
    }
    this.started = true;
    try {
      const saved = localStorage.getItem('rd_active_scenario');
      if (saved) {
        this.activeId.set(saved);
      }
    } catch {
      // ignore private-mode storage
    }
    this.api.getScenarios().subscribe({
      next: (rows) => this.scenarios.set((rows || []).filter((row) => row.id !== 'dog_attack')),
      error: () => this.scenarios.set([]),
    });
  }

  select(id: string): void {
    this.activeId.set(id);
    try {
      localStorage.setItem('rd_active_scenario', id);
    } catch {
      // ignore
    }
  }
}
