import { teamTone } from '../core/maps/map-markers';
import type { StoredResource } from '@rd/shared';

export type TeamBucket = 'free' | 'busy' | 'notUpdated';

/** Mutually exclusive Free / Busy / Not updated (>2h). Not-updated is never free. */
export function teamBucket(team: StoredResource, now = Date.now()): TeamBucket {
  const tone = teamTone(team, now);
  return tone === 'stale' ? 'notUpdated' : tone;
}

export function teamsFreeCounts(teams: StoredResource[], now = Date.now()): {
  free: number;
  busy: number;
  notUpdated: number;
  total: number;
} {
  let free = 0;
  let busy = 0;
  let notUpdated = 0;
  for (const team of teams) {
    const bucket = teamBucket(team, now);
    if (bucket === 'free') free += 1;
    else if (bucket === 'busy') busy += 1;
    else notUpdated += 1;
  }
  return { free, busy, notUpdated, total: teams.length };
}

export function teamsFreeLabel(
  translate: (key: string) => string,
  teams: StoredResource[],
  now = Date.now(),
): string {
  const { free, total } = teamsFreeCounts(teams, now);
  return translate('coord.teamsFreeOf').replace('{f}', String(free)).replace('{t}', String(total));
}
