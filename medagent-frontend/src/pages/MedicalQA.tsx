import React from 'react';
import { useSearchParams } from 'react-router-dom';
import ChatInterface from '../components/ChatInterface';
import { askQuestion } from '../services/api';

const MedicalQA: React.FC = () => {
  const [searchParams] = useSearchParams();
  const initialSessionId = searchParams.get('s') || undefined;
  const initialShowHistory = searchParams.get('show') === 'sessions';

  return (
    <ChatInterface
      title="通用问答"
      subtitle="自动检索所有知识库 - 基于知识库的智能问答系统"
      apiFunction={askQuestion}
      hideKBSelector={true}
      streamEndpoint="/chat/ask/stream"
      initialSessionId={initialSessionId}
      initialShowHistory={initialShowHistory}
      autoLoadLastSession={!initialSessionId}
      sessionType="qa"
    />
  );
};

export default MedicalQA;
