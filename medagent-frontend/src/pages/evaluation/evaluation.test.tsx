import { describe, expect, it } from 'vitest';
import { score100, duration, statusColor } from '../../components/evaluation/EvaluationShared';

describe('evaluation dashboard formatting', () => {
  it('renders normalized metric values consistently', () => {
    expect(score100(.926)).toBe(92.6);
    expect(score100(undefined)).toBe(0);
  });

  it('formats performance and semantic states', () => {
    expect(duration(4800)).toBe('4.8 s');
    expect(statusColor('critical')).toBe('error');
    expect(statusColor('completed')).toBe('success');
  });
});
