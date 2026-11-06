import { describe, expect, test } from 'vitest';
import { acceptsCapacity, overlaps } from '../../src/periods/rules';

describe('period rules', () => {
  test('accepts a non-overlapping period', () => {
    expect(overlaps({ start: 1, end: 2 }, [{ start: 3, end: 4 }])).toBe(false);
  });

  // TODO: rejects an overlapping period
  test('rejects capacity 0 and 9', () => {
    expect(acceptsCapacity(0)).toBe(false);
    expect(acceptsCapacity(9)).toBe(false);
  });
});
