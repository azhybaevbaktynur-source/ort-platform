/**
 * Dependency-free check of the scheme editor helpers.
 * Run (from repo root):
 *   cd frontend && npx tsc --outDir /tmp/agy_f1_check --module commonjs --target es2020 --skipLibCheck \
 *     src/components/lms/grading/schemes/params.ts src/components/lms/grading/schemes/params.check.ts \
 *     && node /tmp/agy_f1_check/components/lms/grading/schemes/params.check.js
 */
import {
  CAPS, cleanParams, defaultParams, fmtNum, fmtPercentile, lookupToCsv, normalizeParams, parseLookupCsv, parseNum, previewRaws,
  segmentValue, sortSchemes, splitLastSegment, stableStringify, toNum, validateParams, type ParamIssue,
} from "./params";
import {
  SCHEME_TYPES, type BandsParams, type CurveParams, type LookupTableParams, type SchemeParams, type SchemeSummaryOut,
} from "../../../../lib/lms/gradingTypes";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}
const codes = (xs: ParamIssue[]) => xs.map((x) => `${x.block}${x.row ? `#${x.row}` : ""}:${x.code}`);
const has = (xs: ParamIssue[], s: string) => codes(xs).includes(s);

// numbers
ok(toNum("12.50") === 12.5 && toNum(null) === null && toNum("x") === null && toNum(3) === 3, "toNum");
ok(parseNum("1,5") === 1.5 && parseNum("") === null && parseNum("-") === null && parseNum("abc") === null, "parseNum");
ok(fmtNum("150.00") === "150" && fmtNum(1.005, 1) === "1" && fmtNum(null) === "", "fmtNum");
ok(fmtPercentile("50") === "50.0" && fmtPercentile(99.94) === "99.9" && fmtPercentile(null) === "", "fmtPercentile one decimal");

// every default is valid and survives cleaning unchanged
for (const t of SCHEME_TYPES) {
  const p = defaultParams(t);
  ok(validateParams(t, p).length === 0, `default ${t} is valid (${codes(validateParams(t, p)).join(" ")})`);
  ok(stableStringify(cleanParams(t, p)) === stableStringify(p), `default ${t} unchanged by cleanParams`);
}

// the seeded ORT main v1 (design 3.1) passes the client checks
const ortMain: CurveParams = {
  schema: 1, scale_min: 60, scale_max: 245,
  segments: [
    { from_ratio: 0, to_ratio: 0.5, from_value: 60, to_value: 150, exponent: 1.05 },
    { from_ratio: 0.5, to_ratio: 1, from_value: 150, to_value: 245, exponent: 0.95 },
  ],
  zero_raw: { value: 0, percentile: 0.0 }, rounding: { mode: "half_even", decimals: 0 },
  percentile: { mean: 150, sd: 30, min: 1.0, max: 99.9, decimals: 1 },
  thresholds: [{ key: "golden_certificate", min_value: 219 }], apply_to_sections: true,
};
ok(validateParams("piecewise_curve", ortMain).length === 0, "ORT main v1 params valid");
ok(stableStringify(cleanParams("piecewise_curve", ortMain)) === stableStringify(ortMain), "ORT main v1 survives cleanParams");
// oracle point: raw 15/30 -> ratio .5 -> 150; raw 30/30 -> 245
ok(segmentValue(ortMain.segments[1], 0.5) === 150 && segmentValue(ortMain.segments[1], 1) === 245, "segmentValue endpoints");
ok(Math.round(segmentValue(ortMain.segments[0], 0.25)) === Math.round(60 + 90 * 0.5 ** 1.05), "segmentValue expression order");

// curve errors
const gap: CurveParams = { ...ortMain, segments: [{ ...ortMain.segments[0], to_ratio: 0.4 }, ortMain.segments[1]] };
ok(has(validateParams("piecewise_curve", gap), "segments#2:segmentsGap"), "curve gap detected");
const late: CurveParams = { ...ortMain, segments: [{ ...ortMain.segments[0], from_ratio: 0.1 }, ortMain.segments[1]] };
ok(has(validateParams("piecewise_curve", late), "segments#1:segmentsStart"), "curve must start at 0");
const short: CurveParams = { ...ortMain, segments: [ortMain.segments[0]] };
ok(has(validateParams("piecewise_curve", short), "segments#1:segmentsEnd"), "curve must end at 1");
ok(has(validateParams("piecewise_curve", { ...ortMain, scale_min: 300 }), "scale:scaleOrder"), "scale order");
ok(has(validateParams("piecewise_curve", { ...ortMain, segments: [{ ...ortMain.segments[0], exponent: 0 }, ortMain.segments[1]] }), "segments#1:exponentPositive"), "exponent > 0");
const many: CurveParams = { ...ortMain, segments: Array.from({ length: 21 }, (_, i) => ({ from_ratio: i / 21, to_ratio: (i + 1) / 21, from_value: 0, to_value: 1, exponent: 1 })) };
ok(validateParams("piecewise_curve", many).some((x) => x.code === "tooMany" && x.max === CAPS.segments), "segments cap 20");

// split keeps contiguity and (for exponent 1) the curve
const lin = defaultParams("piecewise_curve") as CurveParams;
const split = splitLastSegment(lin.segments, 0, 100);
ok(split.length === 2 && split[0].to_ratio === 0.5 && split[1].from_ratio === 0.5 && split[0].to_value === 50, "splitLastSegment halves");
ok(validateParams("piecewise_curve", { ...lin, segments: split }).length === 0, "split curve still valid");

// bands
const bands = defaultParams("bands") as BandsParams;
const unordered: BandsParams = { ...bands, bands: [bands.bands[1], bands.bands[0], bands.bands[2], bands.bands[3]] };
ok(has(validateParams("bands", unordered), "bands#2:bandsOrder"), "bands must descend strictly");
const noZero: BandsParams = { ...bands, bands: bands.bands.slice(0, 3) };
ok(has(validateParams("bands", noZero), "bands#3:bandsLastZero"), "last band must be 0");
const dup: BandsParams = { ...bands, bands: [bands.bands[0], { ...bands.bands[1], key: "5" }, bands.bands[3]] };
ok(has(validateParams("bands", dup), "bands#2:keyDuplicate"), "band keys unique");
const nolabel: BandsParams = { ...bands, bands: [{ ...bands.bands[0], label: { en: " " } }, bands.bands[3]] };
ok(has(validateParams("bands", nolabel), "bands#1:labelRequired"), "band label required");
const longLabel: BandsParams = { ...bands, bands: [{ ...bands.bands[0], label: { ru: "x".repeat(61) } }, bands.bands[3]] };
ok(has(validateParams("bands", longLabel), "bands#1:labelTooLong"), "band label <= 60");
const cleaned = cleanParams("bands", { ...bands, bands: [{ ...bands.bands[0], key: " 5 ", label: { en: " Five ", ru: "" } }, bands.bands[3]] }) as BandsParams;
ok(cleaned.bands[0].key === "5" && stableStringify(cleaned.bands[0].label) === stableStringify({ en: "Five" }), "cleanParams trims bands");

// pass/fail + percent
ok(has(validateParams("pass_fail", { schema: 1, pass_threshold_percent: NaN } as SchemeParams), "pass:required"), "pass_fail threshold required");
ok(has(validateParams("percent", { schema: 1, pass_threshold_percent: 120 } as SchemeParams), "pass:percentRange"), "percent threshold range");
ok(stableStringify(cleanParams("percent", { schema: 1, pass_threshold_percent: null } as SchemeParams)) === stableStringify({ schema: 1 }), "null threshold dropped");
// switching type drops stale fields
ok(!("bands" in (cleanParams("pass_fail", { ...bands, pass_threshold_percent: 50 } as unknown as SchemeParams) as object)), "cleanParams drops other type fields");

// common blocks
ok(has(validateParams("points", { schema: 1, rounding: { mode: "half_up", decimals: 3 } }), "rounding:decimalsRange"), "rounding decimals 0..2");
ok(has(validateParams("points", { schema: 1, percentile: { mean: 1, sd: 0, min: 1, max: 99, decimals: 1 } }), "percentile:sdPositive"), "sd > 0");
ok(has(validateParams("points", { schema: 1, percentile: { mean: 1, sd: 1, min: 50, max: 10, decimals: 1 } }), "percentile:minMax"), "percentile min <= max");
ok(has(validateParams("points", { schema: 1, thresholds: [{ key: "a", min_value: 1 }, { key: "a", min_value: 2 }] }), "thresholds#2:keyDuplicate"), "threshold keys unique");
ok(validateParams("points", { schema: 1, thresholds: Array.from({ length: 11 }, (_, i) => ({ key: `k${i}`, min_value: i })) }).some((x) => x.code === "tooMany"), "thresholds cap 10");
ok(stableStringify(cleanParams("points", { schema: 1, thresholds: [], apply_to_sections: false })) === stableStringify({ schema: 1 }), "empty common blocks dropped");

// lookup table
const lt = (rows: LookupTableParams["rows"], ep: number | null = null): LookupTableParams => ({ schema: 1, rows, expected_possible: ep });
ok(validateParams("lookup_table", lt([{ raw_from: 0, raw_to: 9, value: 60 }, { raw_from: 10, raw_to: 20, value: 100 }], 20)).length === 0, "lookup valid");
ok(has(validateParams("lookup_table", lt([{ raw_from: 1, raw_to: 9, value: 60 }])), "rows#1:rowsStart"), "lookup starts at 0");
ok(has(validateParams("lookup_table", lt([{ raw_from: 0, raw_to: 9, value: 60 }, { raw_from: 9, raw_to: 20, value: 1 }])), "rows#2:rowsOverlap"), "lookup overlap");
ok(has(validateParams("lookup_table", lt([{ raw_from: 0, raw_to: 5, value: 60 }, { raw_from: 9, raw_to: 20, value: 1 }])), "rows#2:rowsGap"), "lookup gap");
ok(has(validateParams("lookup_table", lt([{ raw_from: 0, raw_to: 5, value: 60 }], 10)), "rows#1:rowsCoverage"), "lookup coverage");
ok(has(validateParams("lookup_table", lt([{ raw_from: 0, raw_to: -1, value: 60 }])), "rows#1:rowRange"), "lookup from <= to");
ok(has(validateParams("lookup_table", lt([{ raw_from: 0, raw_to: 9, value: 60 }], 0)), "expected_possible:positive"), "lookup expected_possible 0 rejected");
ok(has(validateParams("lookup_table", lt([{ raw_from: 0, raw_to: 9, value: 60 }], -3)), "expected_possible:positive"), "lookup expected_possible negative rejected");
ok(!validateParams("lookup_table", lt([{ raw_from: 0, raw_to: 9, value: 60 }], 9)).some((x) => x.block === "expected_possible"), "lookup expected_possible > 0 ok");

// CSV
const csv = parseLookupCsv("raw_from,raw_to,value,label\n0,9,60\n10;20;100;top\n\nx,1,2\n21\t30\t150\n");
ok(csv.rows.length === 3 && csv.rows[1].label === "top" && csv.rows[2].value === 150, "CSV rows with header, ; and tab");
ok(csv.badLines.length === 1 && csv.badLines[0] === 5, "CSV bad line reported 1-based");
ok(parseLookupCsv("0,1,2,a,b").rows[0].label === "a,b", "CSV label keeps extra commas");
ok(lookupToCsv([{ raw_from: 0, raw_to: 9, value: 60 }, { raw_from: 10, raw_to: 20, value: 100, label: "top" }]) === "0,9,60\n10,20,100,top", "CSV export");

// preview raws
ok(stableStringify(previewRaws(5)) === "[0,1,2,3,4,5]", "raws 0..N");
ok(stableStringify(previewRaws(2.5)) === "[0,1,2,2.5]", "fractional possible appended");
ok(stableStringify(previewRaws(10, 4)) === "[0,4,8,10]", "step with possible appended");
ok(previewRaws(5000).length <= CAPS.previewRaws && previewRaws(5000)[previewRaws(5000).length - 1] === 5000, "cap 1001 keeps N");
ok(previewRaws(1000).length === 1001, "N=1000 gives 1001 rows");
ok(previewRaws(0).length === 0 && previewRaws(null).length === 0, "no raws for possible <= 0");

// server Decimal strings -> numbers (known numeric keys only; labels and keys untouched)
const norm = normalizeParams({
  schema: 1, scale_min: "60", segments: [{ from_ratio: "0.5", exponent: "0.95" }],
  zero_raw: { value: "0", percentile: "0.0" }, percentile: { mean: "150", sd: "30" },
  rows: [{ raw_from: "0", raw_to: "9", value: "60", label: "10" }], bands: [{ key: "5", label: { ru: "5" }, min_percent: "85" }],
} as unknown as SchemeParams) as unknown as {
  scale_min: unknown; segments: { from_ratio: unknown; exponent: unknown }[];
  zero_raw: { percentile: unknown }; percentile: { mean: unknown };
  rows: { value: unknown; label: unknown }[]; bands: { key: unknown; label: { ru: unknown }; min_percent: unknown }[];
};
ok(norm.scale_min === 60 && norm.segments[0].from_ratio === 0.5 && norm.segments[0].exponent === 0.95, "normalize curve numbers");
ok(norm.zero_raw.percentile === 0 && norm.percentile.mean === 150, "normalize nested blocks");
ok(norm.rows[0].value === 60 && norm.rows[0].label === "10" && norm.bands[0].key === "5" && norm.bands[0].label.ru === "5" && norm.bands[0].min_percent === 85, "normalize leaves labels/keys as strings");

// library order
const sys = (id: string, is_system: boolean) => ({ id, is_system } as SchemeSummaryOut);
ok(sortSchemes([sys("m1", false), sys("s1", true), sys("m2", false), sys("s2", true)]).map((s) => s.id).join() === "s1,s2,m1,m2", "system schemes first");

if (failed) { console.error(`${failed} check(s) failed`); process.exit(1); }
console.log("all checks passed");
