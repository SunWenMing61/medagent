import { describe, expect, it } from 'vitest';

import { parseAnswerContent } from './ChatInterface';


describe('parseAnswerContent', () => {
  it('separates the answer, uncertainty, limits, next step and disclaimer', () => {
    const parsed = parseAnswerContent(`精炼结论：控制血压需要持续随访。

- 定期监测家庭血压。[1]
- 根据医生建议调整生活方式。[2]

不确定性：不同人群的目标范围可能不同。

限制：不能据此自行调整药物。

下一步：携带血压记录咨询医生。

医疗免责声明 / Medical Disclaimer：本信息仅供参考。`);

    expect(parsed.main).toContain('控制血压需要持续随访');
    expect(parsed.main).toContain('定期监测家庭血压');
    expect(parsed.main).not.toContain('免责声明');
    expect(parsed.uncertainty).toBe('不同人群的目标范围可能不同。');
    expect(parsed.limitations).toBe('不能据此自行调整药物。');
    expect(parsed.nextSteps).toBe('携带血压记录咨询医生。');
    expect(parsed.disclaimer).toBe('本信息仅供参考。');
  });

  it('recognizes inline auxiliary sections without losing the core answer', () => {
    const parsed = parseAnswerContent('核心结论：建议记录症状。不确定性：信息仍不完整。限制：不能替代面诊。');

    expect(parsed.main).toBe('建议记录症状。');
    expect(parsed.uncertainty).toBe('信息仍不完整。');
    expect(parsed.limitations).toBe('不能替代面诊。');
  });
});
