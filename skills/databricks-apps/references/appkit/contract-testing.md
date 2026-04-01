# Contract Testing

PACT-style contract tests for AppKit apps. Consumer defines expectations, provider verifies. Use when multiple modules produce or consume the same data shapes.

**When to use:** Multi-module apps, apps with jobs that produce/consume data, or any app where two or more modules share a data boundary. Skip for single-module prototypes.

**Not mandatory.** Add contract tests when the app has multiple producers/consumers of the same data, or when a boundary change has caused a runtime bug.

## What Contract Tests Are

Contract tests verify that a producer's output matches what the consumer expects. They are NOT integration tests -- they run without network calls, databases, or live services.

The pattern (PACT-style):
1. **Consumer** defines a contract: "I expect this shape, with these constraints."
2. **Provider** is verified against that contract: "Does my output satisfy every consumer?"
3. If either side changes, the contract test fails at build time -- not in production.

```
Consumer (Dashboard)              Provider (Eval API)
        |                                 |
        +-- expects scores 0..1           |
        +-- expects run_id as string      |
        +-- expects status enum           |
        |                                 |
        +---- contract.test.ts -----------+
                    |
              vitest runs
              at build time
```

## Contract Boundaries in AppKit Apps

Each module boundary is a potential contract surface:

| Boundary | Producer | Consumer | What to test |
|----------|----------|----------|-------------|
| frontend <-> server | tRPC router | React components | Response shapes, error codes, field presence |
| server <-> lakebase | Lakebase migrations/queries | tRPC procedures | Row shapes, column types, NULL handling |
| server <-> files | Files plugin | tRPC procedures | Volume paths, content types, metadata keys |
| job <-> job | Upstream job task | Downstream job task | Task output shapes, status codes, payload encoding |

## How to Write Contract Tests with Vitest

Contract tests live alongside unit tests and run with `vitest`.

### Basic Example

```ts
import { describe, it, expect } from "vitest";

// Simulated provider response -- in practice, import the type
// and construct a minimal valid instance.
const result = {
  run_id: "run-abc-123",
  appeval100: 0.87,
  status: "COMPLETED",
  metrics: { accuracy: 0.92, latency_ms: 340 },
};

describe("Dashboard expects Eval API", () => {
  it("returns a valid run_id", () => {
    expect(typeof result.run_id).toBe("string");
    expect(result.run_id.length).toBeGreaterThan(0);
  });

  it("returns results with scores between 0 and 1", () => {
    expect(result.appeval100).toBeGreaterThanOrEqual(0);
    expect(result.appeval100).toBeLessThanOrEqual(1);
  });

  it("returns a known status enum value", () => {
    expect(["PENDING", "RUNNING", "COMPLETED", "FAILED"]).toContain(
      result.status
    );
  });

  it("includes metrics as a record of numbers", () => {
    for (const [key, value] of Object.entries(result.metrics)) {
      expect(typeof key).toBe("string");
      expect(typeof value).toBe("number");
    }
  });
});
```

### Testing Lakebase Row Shapes

```ts
import { describe, it, expect } from "vitest";
import type { RunRecord } from "../proto/gen/app/v1/database";

// Minimal valid row -- mirrors what Lakebase would return.
const row: RunRecord = {
  run_id: "run-001",
  app_name: "my-app",
  status: "RUN_STATUS_PENDING",
  started_at: new Date().toISOString(),
  completed_at: "",
  error_message: "",
  config_json: "{}",
};

describe("API module expects RunRecord from Lakebase", () => {
  it("has required fields", () => {
    expect(row.run_id).toBeTruthy();
    expect(row.app_name).toBeTruthy();
  });

  it("status is a valid enum string", () => {
    expect(row.status).toMatch(/^RUN_STATUS_/);
  });

  it("config_json is valid JSON", () => {
    expect(() => JSON.parse(row.config_json)).not.toThrow();
  });
});
```

### Testing Job Task Outputs

```ts
import { describe, it, expect } from "vitest";
import type { JobTaskOutput } from "../proto/gen/app/v1/compute";

const output: JobTaskOutput = {
  task_id: "task-001",
  run_id: "run-001",
  success: true,
  error: "",
  output_payload: new Uint8Array([]),
  duration_ms: 1200,
  metrics: { rows_processed: "5000" },
};

describe("API module expects JobTaskOutput", () => {
  it("has matching run_id and task_id", () => {
    expect(output.run_id).toBeTruthy();
    expect(output.task_id).toBeTruthy();
  });

  it("duration_ms is non-negative", () => {
    expect(output.duration_ms).toBeGreaterThanOrEqual(0);
  });

  it("on success, error is empty", () => {
    if (output.success) {
      expect(output.error).toBe("");
    }
  });
});
```

## Proto-First Contract Derivation

The recommended workflow ties contract tests directly to proto definitions:

```
1. Write the contract test    ->  "Dashboard expects scores 0..1"
2. Derive the proto message   ->  message EvalResult { double score = 1; }
3. Generate TypeScript types  ->  buf generate proto/
4. Implement provider         ->  tRPC route returns EvalResult
5. Contract test passes       ->  Consumer expectation met
```

This inverts the usual flow. Instead of writing the proto first and hoping consumers are satisfied, you start from what the consumer needs and work backward to the schema. The proto becomes the verified bridge.

## Running Contract Tests

Contract tests run with the rest of the vitest suite:

```bash
# Run all tests including contracts
npx vitest run

# Run only contract tests (by convention, name files *.contract.test.ts)
npx vitest run --reporter=verbose "contract"
```

## File Naming Convention

```
tests/
  contracts/
    dashboard-eval-api.contract.test.ts
    api-lakebase-runs.contract.test.ts
    job-upstream-downstream.contract.test.ts
```

Name each file `<consumer>-<provider>.contract.test.ts` so the boundary is obvious at a glance.

## Common Traps

| Trap | Why it fails | Fix |
|------|-------------|-----|
| Testing implementation, not shape | Test breaks on refactor even though contract holds | Assert on shape and constraints, not internal logic |
| No contract for job boundaries | Job output changes silently, downstream breaks | Add contract test for every job->job and job->api boundary |
| Duplicating validation logic | Contract and runtime validation diverge | Derive both from the proto; contract test checks the shape, runtime uses generated validators |
| Testing only happy path | Missing fields or null values slip through | Add cases for empty strings, zero values, missing optional fields |
