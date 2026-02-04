# Unit Testing

## 1. Backend Unit Testing (Python)

### Structure

```python
# tests/unit/test_streak_calculator.py
import pytest
from datetime import date
from app.services.streak import calculate_streak

class TestStreakCalculation:
    def test_returns_zero_for_empty_completions(self):
        result = calculate_streak([])
        assert result == 0

    def test_returns_one_for_single_completion_today(self):
        result = calculate_streak([date.today()])
        assert result == 1

    def test_counts_consecutive_days(self):
        completions = [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)]
        result = calculate_streak(completions)
        assert result == 3

    def test_breaks_on_gap(self):
        completions = [date(2025, 1, 1), date(2025, 1, 3)]  # Gap on Jan 2
        result = calculate_streak(completions)
        assert result == 1  # Only Jan 3 counts
```

### Parametrized Tests

```python
@pytest.mark.parametrize("completions,expected", [
    ([], 0),
    ([date(2025, 1, 1)], 1),
    ([date(2025, 1, 1), date(2025, 1, 2)], 2),
    ([date(2025, 1, 1), date(2025, 1, 3)], 1),  # Gap breaks streak
])
def test_streak_calculation(completions, expected):
    assert calculate_streak(completions) == expected
```

### Mocking

```python
from unittest.mock import Mock, patch

def test_service_calls_repository():
    mock_repo = Mock()
    mock_repo.get_by_id.return_value = Habit(id=1, name="Exercise")

    service = HabitService(repository=mock_repo)
    result = service.get_habit(1)

    mock_repo.get_by_id.assert_called_once_with(1)
    assert result.name == "Exercise"
```

### Running Backend Unit Tests

```bash
pytest tests/unit
pytest -m unit
```

---

## 2. Frontend Unit Testing (React Components)

### Setup with Vitest

```javascript
// vite.config.js
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
  },
});

// src/test/setup.js
import '@testing-library/jest-dom';
```

### Component Tests

```javascript
// src/features/habits/__tests__/HabitCard.test.jsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HabitCard } from '../components/HabitCard';

describe('HabitCard', () => {
  const mockHabit = {
    id: 1,
    name: 'Exercise',
    currentStreak: 5,
    completedToday: false,
  };

  it('renders habit name', () => {
    render(<HabitCard habit={mockHabit} />);

    expect(screen.getByText('Exercise')).toBeInTheDocument();
  });

  it('displays current streak', () => {
    render(<HabitCard habit={mockHabit} />);

    expect(screen.getByText(/5.*streak/i)).toBeInTheDocument();
  });

  it('calls onComplete when button clicked', async () => {
    const onComplete = vi.fn();
    render(<HabitCard habit={mockHabit} onComplete={onComplete} />);

    await userEvent.click(screen.getByRole('button', { name: /complete/i }));

    expect(onComplete).toHaveBeenCalledWith(1);
  });

  it('shows completed state', () => {
    const completedHabit = { ...mockHabit, completedToday: true };
    render(<HabitCard habit={completedHabit} />);

    expect(screen.getByRole('button')).toBeDisabled();
  });
});
```

### Quick Reference

**Query Priority (Use in Order)**
1. `getByRole` - Accessible name (best)
2. `getByLabelText` - Form labels
3. `getByText` - Text content
4. `getByTestId` - Last resort

**Assertion Cheatsheet**

```javascript
// React Testing Library
expect(element).toBeInTheDocument();
expect(element).toBeVisible();
expect(element).toHaveText('text');
expect(element).toBeDisabled();
expect(mockFn).toHaveBeenCalledWith(arg);
```

### Running Frontend Tests

```bash
npm test
npm test -- --watch
```
