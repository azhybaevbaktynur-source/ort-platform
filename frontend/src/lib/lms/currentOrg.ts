// Item 4 (ADMIN_ORGS_DESIGN §2.5): the organization `OrgShell` has loaded, for the header's organization switcher.
// `OrgShell` sets it after `GET /org/{id}` and clears it on unmount, so the header makes no request of its own.
// The URL stays the state of the selection; this only carries the name and how the caller acts there.
import { useSyncExternalStore } from "react";
import type { OrgActingAs } from "./organizations";

export interface CurrentOrg {
  id: string;
  name: string;
  acting_as: OrgActingAs;
}

let current: CurrentOrg | null = null;
const listeners = new Set<() => void>();

export function setCurrentOrg(org: CurrentOrg | null): void {
  const same = org === current
    || (!!org && !!current && org.id === current.id && org.name === current.name && org.acting_as === current.acting_as);
  if (same) return;
  current = org;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

const snapshot = () => current;
const serverSnapshot = () => null;

/** The organization open in `/org/{id}` right now, or null. */
export function useCurrentOrg(): CurrentOrg | null {
  return useSyncExternalStore(subscribe, snapshot, serverSnapshot);
}
