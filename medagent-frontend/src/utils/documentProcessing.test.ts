import { describe, expect, it } from 'vitest';

import type { Document } from '../services/api';
import {
  getDocumentPipelineStatus,
  getDocumentProgress,
  getDocumentProgressMessage,
} from './documentProcessing';

const document = (overrides: Partial<Document>): Document => ({
  id: 106,
  filename: 'large.pdf',
  kb_id: 1,
  status: 'success',
  ...overrides,
});

describe('document processing presentation', () => {
  it('does not report parse success as full completion when vectorization failed', () => {
    const failed = document({
      parse_status: 'success',
      vector_status: 'failed',
      processing_progress: 92,
      processing_message: '任务失败: SSL EOF',
      error_message: 'Embedding network failure: SSL EOF',
    });

    expect(getDocumentPipelineStatus(failed)).toBe('failed');
    expect(getDocumentProgress(failed)).toBe(92);
    expect(getDocumentProgressMessage(failed)).toContain('Embedding network failure');
  });

  it('uses vector success as the authoritative terminal state', () => {
    const completed = document({
      parse_status: 'success',
      vector_status: 'success',
      processing_progress: 92,
      processing_message: '旧任务失败消息',
    });

    expect(getDocumentPipelineStatus(completed)).toBe('success');
    expect(getDocumentProgress(completed)).toBe(100);
    expect(getDocumentProgressMessage(completed)).toBe('解析、分块和向量入库完成');
  });
});
