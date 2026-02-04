# E2E Testing with Playwright

## 1. Playwright MCP Server Setup

```bash
use playwright mcp server
```

## 2. Configuration

```javascript
// playwright.config.js
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
  },
});
```

## 3. Page Object Model

```javascript
// tests/e2e/pages/DashboardPage.js
export class DashboardPage {
  constructor(page) {
    this.page = page;
    this.addHabitButton = page.getByRole('button', { name: /add habit/i });
    this.habitList = page.getByTestId('habit-list');
  }

  async goto() {
    await this.page.goto('/');
  }

  async addHabit(name) {
    await this.addHabitButton.click();
    await this.page.getByLabel('Habit name').fill(name);
    await this.page.getByRole('button', { name: /save/i }).click();
  }

  async completeHabit(name) {
    const habitCard = this.page.getByTestId(`habit-${name}`);
    await habitCard.getByRole('button', { name: /complete/i }).click();
  }

  async getHabitStreak(name) {
    const habitCard = this.page.getByTestId(`habit-${name}`);
    return habitCard.getByTestId('streak-count').textContent();
  }
}
```

## 4. E2E Tests

```javascript
// tests/e2e/habits.spec.js
import { test, expect } from '@playwright/test';
import { DashboardPage } from './pages/DashboardPage';

test.describe('Habit Tracking', () => {
  test('user can create and complete a habit', async ({ page }) => {
    const dashboard = new DashboardPage(page);

    await dashboard.goto();
    await dashboard.addHabit('Exercise');

    // Verify habit appears
    await expect(page.getByText('Exercise')).toBeVisible();

    // Complete the habit
    await dashboard.completeHabit('Exercise');

    // Verify streak updated
    await expect(page.getByTestId('streak-count')).toHaveText('1');
  });

  test('streak increments on consecutive days', async ({ page }) => {
    // Test with seeded data for multi-day scenarios
  });
});
```

## 5. Visual Testing

```javascript
test('dashboard matches snapshot', async ({ page }) => {
  await page.goto('/');

  // Wait for data to load
  await expect(page.getByTestId('habit-list')).toBeVisible();

  // Compare screenshot
  await expect(page).toHaveScreenshot('dashboard.png', {
    mask: [page.locator('.timestamp')],  // Mask dynamic content
  });
});
```

## 6. Strict Data Integrity & Contract Validation

> [!IMPORTANT]
> The AI agent must treat the Backend as the "Source of Truth" for all data structures during E2E testing. Move beyond "visibility" tests and ensure the contract between Frontend and Backend is actually working.

### 1. Content over Visibility

Never rely solely on `toBeVisible()`. Always verify that the content is present and valid.

```javascript
// ❌ Weak Assertion
await expect(page.getByTestId('username')).toBeVisible();

// ✅ Strong Assertion
await expect(page.getByTestId('username')).not.toBeEmpty();
await expect(page.getByTestId('username')).toHaveText(/^[a-zA-Z0-9_]+$/);
```

### 2. Network/Contract Validation

When a critical action occurs (e.g., submitting a form), use `waitForResponse` to verify the API contract.

```javascript
// Start waiting for response BEFORE the action
const responsePromise = page.waitForResponse(resp => 
  resp.url().includes('/api/habits') && resp.status() === 201
);

// Perform action
await page.getByRole('button', { name: /save/i }).click();

// Await response and verify body
const response = await responsePromise;
const json = await response.json();

expect(json).toHaveProperty('id');
expect(json).not.toHaveProperty('error');
```

### 2.1 Code Template: Robust API Contract Validation

// Use this pattern to prevent "Silent Failures" where the UI shows success but data is missing.

```javascript
test('should verify API contract integrity during action', async ({ page }) => {
  const dashboard = new DashboardPage(page);
  await dashboard.goto();

  // 1. Set up the network listener BEFORE the action
  const responsePromise = page.waitForResponse(response => 
    response.url().includes('/api/habits') && 
    response.request().method() === 'POST'
  );

  // 2. Trigger the action
  await dashboard.addHabit('New Habit');

  // 3. Capture and validate the response payload
  const response = await responsePromise;
  const body = await response.json();

  // ✅ Validation: Catch "Contract Mismatches" (like message vs query)
  expect(response.status()).toBe(201);
  expect(body).toHaveProperty('id');
  expect(body).toHaveProperty('answer'); // Ensure this matches your backend schema!
  
  // 4. Final UI Integrity Check
  await expect(page.getByText('New Habit')).not.toBeEmpty();
});
```

### 3. Error Handling Rules

- **422 Unprocessable Entity**: If a test fails with 422, you MUST immediately cross-reference the Frontend payload with the Backend `schemas.py`.
- **Empty State Prevention**: A "Success" UI element with undefined text is a critical failure.
  ```javascript
  // Ensure we didn't render an empty bubble
  await expect(page.locator('.success-message')).toHaveText(/success/i);
  ```

## 7. Running E2E Tests

```bash
# Run all E2E tests
npx playwright test

# Run with UI mode (debugging)
npx playwright test --ui

# Run specific test file
npx playwright test habits.spec.js

# Update snapshots
npx playwright test --update-snapshots
```

## Assertion Cheatsheet

```javascript
# Playwright
await expect(locator).toBeVisible();
await expect(locator).toHaveText('text');
await expect(page).toHaveURL('/path');
await expect(page).toHaveScreenshot();
```
