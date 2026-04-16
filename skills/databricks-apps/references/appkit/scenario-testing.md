# Scenario Testing (pw-evals)

Playwright end-to-end tests parameterized by JSON test cases. Use for apps that need UI-level acceptance testing across multiple input/output scenarios.

**When to use:** Apps with deterministic user workflows where you can define input/output pairs. Particularly useful for evaluation-driven development where an agent builds the app and automated tests verify correctness.

**Not mandatory.** Add scenario tests when the app needs UI-level acceptance testing beyond smoke tests.

## What Scenario Tests Are

Scenario tests combine Playwright browser automation with JSON-defined test cases. Each case specifies inputs to enter and expected outputs to verify. The same Playwright spec runs once per case, producing a pass/fail for each.

```
cases.json          +     spec.ts           =    scenario test
(what to test)            (how to test)          (automated verdict)
```

This separates **test data** (cases) from **test logic** (spec), so you can add new scenarios without writing new test code.

## Directory Structure

Each task (a testable unit of the app) gets its own directory:

```
pw-evals/
  task-name/
    meta.json             # Task metadata: appCommand, appUrl, timeout
    public/
      cases.json          # Dev verification cases (visible to agent)
    private/
      cases.json          # Evaluation cases (hidden from agent)
    tests/
      task-name.spec.ts   # Playwright test spec
```

### meta.json

Defines how to start the app and where to find it:

```json
{
  "appCommand": "npm run dev",
  "appUrl": "http://localhost:5173",
  "timeout": 30000
}
```

| Field | Purpose |
|-------|---------|
| `appCommand` | Shell command to start the app (run before tests) |
| `appUrl` | URL Playwright navigates to |
| `timeout` | Max milliseconds per test case |

## How to Write cases.json

Each case is an object with `inputs` (what to enter/select in the UI) and `expected` (what to verify in the UI after the action completes).

```json
[
  {
    "id": "basic-addition",
    "description": "Adds two positive numbers",
    "inputs": {
      "operand_a": "5",
      "operand_b": "3",
      "operation": "add"
    },
    "expected": {
      "result": "8"
    }
  },
  {
    "id": "division-by-zero",
    "description": "Shows error on division by zero",
    "inputs": {
      "operand_a": "10",
      "operand_b": "0",
      "operation": "divide"
    },
    "expected": {
      "error": "Cannot divide by zero"
    }
  }
]
```

### Case Design Rules

- **Each case is independent** -- no case depends on state from a previous case.
- **Inputs map to UI controls** -- field names match ARIA labels or test IDs in the app.
- **Expected values are exact strings** -- the spec asserts equality, not fuzzy matching.
- **Keep cases minimal** -- test one behavior per case. Combine related assertions in `expected`, not multiple behaviors.

## How to Write the Playwright Spec

The spec loads `cases.json`, loops over each case, and uses ARIA selectors to interact with the app.

```ts
import { test, expect } from "@playwright/test";
import cases from "../public/cases.json";

const CASES_PATH = process.env.TASK_CASES_PATH || "public/cases.json";

// Dynamically load cases based on environment variable
const loadCases = async () => {
  const path = require("path").resolve(__dirname, "..", CASES_PATH);
  return require(path);
};

test.describe("Calculator scenarios", () => {
  for (const testCase of cases) {
    test(`${testCase.id}: ${testCase.description}`, async ({ page }) => {
      await page.goto(process.env.APP_URL || "http://localhost:5173");

      // Fill inputs using ARIA selectors
      for (const [field, value] of Object.entries(testCase.inputs)) {
        await page.getByRole("textbox", { name: field }).fill(value as string);
      }

      // If there's a select/dropdown input
      if (testCase.inputs.operation) {
        await page
          .getByRole("combobox", { name: "operation" })
          .selectOption(testCase.inputs.operation);
      }

      // Trigger the action
      await page.getByRole("button", { name: /calculate|submit/i }).click();

      // Verify expected outputs
      for (const [field, value] of Object.entries(testCase.expected)) {
        await expect(
          page.getByRole("status").or(page.getByTestId(field))
        ).toContainText(value as string);
      }
    });
  }
});
```

### Selector Strategy

Use ARIA roles and accessible names, not CSS selectors:

| UI Element | Selector |
|-----------|----------|
| Text input | `page.getByRole("textbox", { name: "field_name" })` |
| Button | `page.getByRole("button", { name: /pattern/i })` |
| Dropdown | `page.getByRole("combobox", { name: "field_name" })` |
| Output text | `page.getByRole("status")` or `page.getByTestId("field")` |
| Heading | `page.getByRole("heading", { name: "text" })` |

This makes tests resilient to CSS and layout changes.

## Public vs Private Split

The split enables evaluation-driven development:

| Set | Who sees it | Purpose |
|-----|------------|---------|
| `public/cases.json` | Agent + developer | Development and debugging. Agent uses these to verify its implementation works. |
| `private/cases.json` | Evaluator only | Grading. Hidden from the agent during development to prevent overfitting. |

Both files have the same schema. The difference is visibility:
- During development, the agent runs tests against `public/cases.json`.
- During evaluation, the harness runs tests against `private/cases.json`.
- If the app handles public cases correctly, it should generalize to private cases (assuming cases test the same behaviors).

## Running Scenario Tests

```bash
# Run with public (dev) cases
TASK_CASES_PATH=public/cases.json npx playwright test

# Run with private (eval) cases
TASK_CASES_PATH=private/cases.json npx playwright test

# Run a specific task
TASK_CASES_PATH=public/cases.json npx playwright test pw-evals/calculator/tests/

# Run with visible browser (debugging)
TASK_CASES_PATH=public/cases.json npx playwright test --headed
```

### Playwright Configuration

Add to `playwright.config.ts`:

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./pw-evals",
  timeout: 30_000,
  use: {
    baseURL: process.env.APP_URL || "http://localhost:5173",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
  },
});
```

## Adding a New Task

1. Create the directory: `pw-evals/<task-name>/`
2. Write `meta.json` with app startup config.
3. Write `public/cases.json` with 3-5 representative cases.
4. Write the Playwright spec in `tests/<task-name>.spec.ts`.
5. Run against public cases to verify.
6. Optionally add `private/cases.json` with additional edge cases for evaluation.

## Common Traps

| Trap | Why it fails | Fix |
|------|-------------|-----|
| Cases depend on execution order | Flaky tests when run in parallel | Make each case fully independent |
| CSS selectors in specs | Tests break on style changes | Use ARIA roles and accessible names |
| Hardcoded URLs | Fails in CI or different environments | Use `process.env.APP_URL` with fallback |
| Too many cases in public set | Agent overfits to specific inputs | Keep public set small (3-5 cases), test general behaviors |
| No timeout per case | Slow cases block the entire suite | Set `timeout` in meta.json and Playwright config |
| Asserting exact layout | Brittle to responsive changes | Assert on text content, not position or size |
