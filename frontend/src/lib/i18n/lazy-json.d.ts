// S5 performance: `import("./ru.json?lazy")` in context.tsx is a module of its own for webpack (the query makes it one),
// so the whole dictionary stays in a lazily loaded chunk while small static uses of the same file (mascot/staticText.ts)
// keep only the parts they read.
declare module "*.json?lazy" {
  const dictionary: Record<string, unknown>;
  export default dictionary;
}
