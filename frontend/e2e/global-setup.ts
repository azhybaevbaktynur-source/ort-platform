import fs from "node:fs";
import { seedPath } from "./helpers";

/** The backend answers /health before the seed is done: wait for seed.json (the seed writes it last). */
export default async function globalSetup(): Promise<void> {
  const file = seedPath();
  const end = Date.now() + 240_000;
  while (Date.now() < end) {
    if (fs.existsSync(file)) return;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`e2e: ${file} did not appear; see the backend log next to it`);
}
