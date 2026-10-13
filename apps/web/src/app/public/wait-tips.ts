/** Same three bullets the status API returns, so the form can show them before classification. */

const RESCUE = ['status.tipHigh', 'status.tipWires', 'status.tipPhone'];
const MEDICAL = ['status.tipMedical1', 'status.tipMedical2', 'status.tipMedical3'];
const FOOD = ['status.tipFood1', 'status.tipFood2', 'status.tipFood3'];
const SHELTER = ['status.tipShelter1', 'status.tipShelter2', 'status.tipShelter3'];
const DOG = ['status.tipDog1', 'status.tipDog2', 'status.tipDog3'];
const DEFAULT = ['status.tipDefault1', 'status.tipDefault2', 'status.tipDefault3'];

function kindOf(incidentType: string | null | undefined): string {
  return (incidentType || '').trim().toLowerCase().replace(/-/g, '_').replace(/ /g, '_');
}

/** Classified type, or the type the reporter picked before classification. */
export function waitTipsFor(incidentType: string | null | undefined): string[] {
  const kind = kindOf(incidentType);
  if (kind === 'animal_attack' || kind === 'dog' || kind === 'dog_attack' || kind === 'dog_bite' || kind.startsWith('dog')) {
    return [...DOG];
  }
  if (kind === 'food' || kind === 'food_water' || kind === 'drinking_water' || kind.startsWith('food')) {
    return [...FOOD];
  }
  if (kind === 'shelter' || kind.includes('shelter')) return [...SHELTER];
  if (kind === 'medical' || kind.startsWith('medic')) return [...MEDICAL];
  if (kind === 'rescue' || kind === 'flood' || kind === 'water_rising' || kind.includes('flood')) {
    return [...RESCUE];
  }
  return [...DEFAULT];
}
