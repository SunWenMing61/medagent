import type { Document } from '../services/api';

export type DocumentPipelineStatus = 'pending' | 'processing' | 'success' | 'failed';

const normalize = (value?: string | null) => String(value || '').toLowerCase();

/**
 * 文档只有在向量写入成功后才算完整完成。解析成功只是中间阶段，不能
 * 覆盖向量化失败，否则页面会同时显示“已完成”和“处理失败”。
 */
export const getDocumentPipelineStatus = (doc: Document): DocumentPipelineStatus => {
  const parseStatus = normalize(doc.parse_status || doc.status);
  const vectorStatus = normalize(doc.vector_status);

  if (vectorStatus === 'success' || vectorStatus === 'completed') return 'success';
  if (parseStatus === 'failed' || parseStatus === 'error' || vectorStatus === 'failed' || vectorStatus === 'error') {
    return 'failed';
  }
  if (
    parseStatus === 'processing' ||
    vectorStatus === 'processing' ||
    (parseStatus === 'success' && (!vectorStatus || vectorStatus === 'pending'))
  ) {
    return 'processing';
  }
  return 'pending';
};

export const getDocumentProgress = (doc: Document): number => {
  if (getDocumentPipelineStatus(doc) === 'success') return 100;
  const value = Number(doc.processing_progress ?? 0);
  return Math.max(0, Math.min(99, Number.isFinite(value) ? value : 0));
};

export const getDocumentProgressMessage = (doc: Document): string => {
  const status = getDocumentPipelineStatus(doc);
  if (status === 'success') return '解析、分块和向量入库完成';
  if (status === 'failed') return doc.error_message || doc.processing_message || '处理失败';
  return doc.processing_message || '等待后台处理';
};
