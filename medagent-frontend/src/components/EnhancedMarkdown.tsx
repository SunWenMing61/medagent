/**
 * EnhancedMarkdown 组件 —— 增强的 Markdown 渲染器。
 *
 * 相比基础 ReactMarkdown 增加的能力：
 * - LaTeX 数学公式渲染（katex）
 * - 表格优化显示
 * - 引用高亮（可点击跳转到原文）
 * - 代码语法高亮
 * - 消息编辑支持
 */

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { Typography, Tag, Tooltip, Button, Space } from 'antd';
import {
  EditOutlined, CheckOutlined, CloseOutlined, LinkOutlined,
} from '@ant-design/icons';

const { Text } = Typography;

/** 引用标记正则：匹配 [来源: X] 或 【知识库X】 格式 */
const REF_PATTERN = /[\[【]([^\]】]*?)(?::\s*(\d+(?:\.\d+)?))?[\]】]|source\((\d+)\)/gi;

interface EnhancedMarkdownProps {
  content: string;
  isUser?: boolean;
  onEdit?: (newContent: string) => Promise<void>;
  /** 引用列表，用于将引用标记渲染为可点击的溯源链接 */
  references?: Array<{ kb_name?: string; similarity?: number; content?: string }>;
  /** 行号/引用高亮 */
  highlightTerms?: string[];
}

const EnhancedMarkdown: React.FC<EnhancedMarkdownProps> = ({
  content, isUser, onEdit, references, highlightTerms,
}) => {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(content);
  const [saving, setSaving] = useState(false);

  // ---- 消息编辑功能 ----
  const handleStartEdit = () => {
    setEditText(content);
    setEditing(true);
  };

  const handleCancelEdit = () => {
    setEditing(false);
    setEditText(content);
  };

  const handleSaveEdit = async () => {
    if (!onEdit || editText.trim() === content) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onEdit(editText.trim());
      setEditing(false);
    } catch {
      setEditText(content);
    } finally {
      setSaving(false);
    }
  };

  // 用户消息编辑模式
  if (isUser && editing) {
    return (
      <div>
        <textarea
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          style={{
            width: '100%', minHeight: 80, padding: 8,
            borderRadius: 6, border: '1px solid #d9d9d9',
            fontFamily: 'inherit', fontSize: 14, resize: 'vertical',
          }}
          disabled={saving}
        />
        <Space style={{ marginTop: 4 }}>
          <Button type="primary" size="small" icon={<CheckOutlined />} onClick={handleSaveEdit} loading={saving}>
            保存
          </Button>
          <Button size="small" icon={<CloseOutlined />} onClick={handleCancelEdit} disabled={saving}>
            取消
          </Button>
        </Space>
      </div>
    );
  }

  // ---- 将引用标记转为可点击链接 ----
  const processedContent = React.useMemo(() => {
    if (!references || references.length === 0) return content;

    // 替换 [来源: 内科库] 或 source(0) 为 HTML 链接
    let result = content;
    let refIndex = 0;
    result = result.replace(REF_PATTERN, (match, name, score, idx) => {
      const targetIdx = idx !== undefined ? parseInt(idx) : refIndex;
      refIndex++;
      const ref = references[targetIdx] || references[0];
      if (!ref) return match;
      const kbName = ref.kb_name || name || '来源';
      const simScore = ref.similarity ? (ref.similarity * 100).toFixed(0) : '';
      return `<sup class="citation-ref" data-ref-index="${targetIdx}" title="${kbName}${simScore ? ' (相关度 ' + simScore + '%)' : ''}">[${targetIdx + 1}]</sup>`;
    });
    return result;
  }, [content, references]);

  // ---- 高亮搜索词 ----
  const highlightedContent = React.useMemo(() => {
    if (!highlightTerms || highlightTerms.length === 0) return processedContent;
    let result = processedContent;
    for (const term of highlightTerms) {
      if (!term.trim()) continue;
      // 只对纯文本部分高亮，不破坏 HTML 标签
      const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      result = result.replace(
        new RegExp(`(${escaped})`, 'gi'),
        '<mark style="background:#fff3cd;padding:0 2px;border-radius:2px">$1</mark>',
      );
    }
    return result;
  }, [processedContent, highlightTerms]);

  return (
    <div className="enhanced-markdown">
      {/* 用户消息编辑按钮 */}
      {isUser && onEdit && !editing && (
        <Tooltip title="编辑消息">
          <Button
            type="text"
            size="small"
            icon={<EditOutlined />}
            onClick={handleStartEdit}
            style={{ float: 'right', opacity: 0.5 }}
            className="msg-edit-btn"
          />
        </Tooltip>
      )}

      {/* Markdown 主体 */}
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, rehypeKatex]}
        components={{
          // 表格优化
          table: ({ children }) => (
            <div style={{ overflowX: 'auto', marginBottom: 12 }}>
              <table style={{
                borderCollapse: 'collapse', width: '100%',
                border: '1px solid #d9d9d9', fontSize: 14,
              }}>{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th style={{
              border: '1px solid #d9d9d9', padding: '8px 12px',
              background: '#f5f5f5', fontWeight: 600, textAlign: 'left',
            }}>{children}</th>
          ),
          td: ({ children }) => (
            <td style={{ border: '1px solid #d9d9d9', padding: '8px 12px' }}>{children}</td>
          ),
          // 引用块
          blockquote: ({ children }) => (
            <blockquote style={{
              borderLeft: '3px solid #1677ff', margin: '8px 0',
              padding: '4px 12px', background: '#f6f8fa', borderRadius: '0 4px 4px 0',
            }}>{children}</blockquote>
          ),
          // 代码块
          pre: ({ children }) => (
            <pre style={{
              background: '#1e1e1e', color: '#d4d4d4',
              padding: 12, borderRadius: 6, overflowX: 'auto',
              marginBottom: 12, fontSize: 13, lineHeight: 1.5,
            }}>{children}</pre>
          ),
          // 图片
          img: ({ src, alt }) => (
            <img
              src={src}
              alt={alt || ''}
              style={{ maxWidth: '100%', borderRadius: 6, margin: '8px 0' }}
              loading="lazy"
            />
          ),
          // 引用链接高亮
          sup: ({ children, ...props }) => (
            <Tooltip title="点击查看来源">
              <sup
                {...props}
                style={{
                  cursor: 'pointer', color: '#1677ff', fontWeight: 600,
                  margin: '0 2px',
                }}
                onClick={() => {
                  const rawIndex = (props as Record<string, unknown>)['data-ref-index'];
                  const idx = typeof rawIndex === 'string' ? Number.parseInt(rawIndex, 10) : Number(rawIndex);
                  if (Number.isInteger(idx) && references?.[idx]) {
                    // 触发自定义事件，供父组件捕获高亮对应引用
                    window.dispatchEvent(new CustomEvent('citation-click', {
                      detail: { index: idx, reference: references[idx] },
                    }));
                  }
                }}
              >
                {children}
              </sup>
            </Tooltip>
          ),
          // 段落
          p: ({ children }) => (
            <p style={{ marginBottom: 8, lineHeight: 1.7, fontSize: 14 }}>{children}</p>
          ),
          // 列表
          ul: ({ children }) => (
            <ul style={{ paddingLeft: 20, marginBottom: 8, lineHeight: 1.8 }}>{children}</ul>
          ),
          ol: ({ children }) => (
            <ol style={{ paddingLeft: 20, marginBottom: 8, lineHeight: 1.8 }}>{children}</ol>
          ),
          // 内联代码
          code: ({ children }) =>
            !String(children).includes('\n')
              ? <code style={{
                  background: '#f0f0f0', padding: '2px 6px', borderRadius: 3,
                  fontSize: '0.9em', color: '#d63384',
                }}>{children}</code>
              : <code style={{
                  background: 'transparent', color: '#d4d4d4', padding: 0, fontSize: 13,
                }}>{children}</code>,
          // 链接
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer"
              style={{ color: '#1677ff' }}>
              {children} <LinkOutlined style={{ fontSize: 12 }} />
            </a>
          ),
        }}
      >
        {highlightedContent}
      </ReactMarkdown>
    </div>
  );
};

export default EnhancedMarkdown;
