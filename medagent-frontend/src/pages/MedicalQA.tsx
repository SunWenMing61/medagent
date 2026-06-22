// 引入 React 核心库
import React from 'react';
// 引入 React Router 的 useSearchParams Hook，用于读取 URL 查询参数
import { useSearchParams } from 'react-router-dom';
// 引入通用聊天界面组件，提供问答对话的 UI 交互
import ChatInterface from '../components/ChatInterface';
// 引入后端通用问答 API 函数
import { askQuestion } from '../services/api';

// 定义 MedicalQA（通用问答）页面组件，类型为 React.FC
const MedicalQA: React.FC = () => {
  // useSearchParams 返回 URL 查询参数对象，用于读取 ?s=xxx 和 ?show=sessions 等参数
  const [searchParams] = useSearchParams();
  // 从 URL 参数中读取会话 ID（?s=会话ID），用于加载指定的历史会话；若无则设为 undefined
  const initialSessionId = searchParams.get('s') || undefined;
  // 从 URL 参数中判断是否需要显示会话历史列表（?show=sessions），返回布尔值
  const initialShowHistory = searchParams.get('show') === 'sessions';

  // 渲染 ChatInterface 组件，传入所有必需的配置 props
  return (
    <ChatInterface
      // 聊天界面标题：显示为 "通用问答"
      title="通用问答"
      // 副标题：简要说明功能范围
      subtitle="自动检索所有知识库 - 基于知识库的智能问答系统"
      // API 请求函数：当用户发送消息时调用 askQuestion（向 /chat/ask 发 POST 请求）
      apiFunction={askQuestion}
      // 隐藏知识库选择器（通用问答默认检索所有知识库，不需要用户手动选择）
      hideKBSelector={true}
      // 流式响应的 SSE 端点路径，用于实时逐字显示 AI 回复
      streamEndpoint="/chat/ask/stream"
      // 从 URL 参数中获取的初始会话 ID，用于加载特定历史会话
      initialSessionId={initialSessionId}
      // 是否初始显示会话历史列表
      initialShowHistory={initialShowHistory}
      // 如果没有通过 URL 指定会话 ID，则自动加载最近的会话记录
      autoLoadLastSession={!initialSessionId}
      // 会话类型标记为 "qa"，用于区分不同类型的会话存储和展示
      sessionType="qa"
    />
  );
};

// 导出 MedicalQA 组件供路由使用
export default MedicalQA;
