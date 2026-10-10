import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/** Guardrail: demo fixtures must come from the API (labelled synthetic), never be hardcoded in the UI. */
function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "__tests__" ? [] : walk(p);
    return /\.(tsx?|ts)$/.test(f) ? [p] : [];
  });
}

describe("no hardcoded demo data in the frontend", () => {
  it("does not embed synthetic repository or contributor fixtures", () => {
    const banned = ["demo-org/", "aurora-api", "nebula-web", "quasar-ml", "ada-lovelace", "atlas-cli"];
    const offenders: string[] = [];
    for (const file of walk(join(process.cwd(), "src"))) {
      const text = readFileSync(file, "utf8");
      for (const b of banned) if (text.includes(b)) offenders.push(`${file}: ${b}`);
    }
    expect(offenders).toEqual([]);
  });
});
