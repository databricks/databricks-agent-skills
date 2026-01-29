# Testing Guidelines

## Unit Tests (Vitest)

**CRITICAL**: Use vitest for all tests. Put tests next to the code (e.g. src/\*.test.ts)

```typescript
import { describe, it, expect } from 'vitest';

describe('Feature Name', () => {
  it('should do something', () => {
    expect(true).toBe(true);
  });

  it('should handle async operations', async () => {
    const result = await someAsyncFunction();
    expect(result).toBeDefined();
  });
});
```

**Best Practices:**
- Use `describe` blocks to group related tests
- Use `it` for individual test cases
- Use `expect` for assertions
- Tests run with `npm test` (runs `vitest run`)

❌ **Do not write unit tests for:**
- SQL files under `config/queries/` - little value in testing static SQL
- Types associated with queries - these are just schema definitions

## Smoke Test (Playwright)

The template includes a smoke test at `tests/smoke.spec.ts` that verifies the app loads correctly.

**⚠️ MUST UPDATE after customizing the app** - the default test checks for template-specific content ('Minimal Databricks App', 'hello world') which won't exist in your app.

```typescript
// tests/smoke.spec.ts - update these selectors:

// ❌ Template default - will fail after customization
await expect(page.getByRole('heading', { name: 'Minimal Databricks App' })).toBeVisible();
await expect(page.getByText('hello world')).toBeVisible();

// ✅ Update to match YOUR app
await expect(page.getByRole('heading', { name: 'Your App Title' })).toBeVisible();
await expect(page.locator('h1').first()).toBeVisible({ timeout: 30000 });  // Or just check any h1
```

**What the smoke test does:**
- Opens the app
- Waits for data to load (SQL query results)
- Verifies key UI elements are visible
- Captures screenshots and console logs to `.smoke-test/` directory
- Always captures artifacts, even on test failure

**Keep smoke tests simple:**
- Only verify that the app loads and displays initial data
- Wait for key elements to appear (page title, main content)
- Capture artifacts for debugging
- Run quickly (< 5 seconds)

**For extended E2E tests:**
- Create separate test files in `tests/` directory (e.g., `tests/user-flow.spec.ts`)
- Use `npm run test:e2e` to run all Playwright tests
- Keep complex user flows, interactions, and edge cases out of the smoke test
