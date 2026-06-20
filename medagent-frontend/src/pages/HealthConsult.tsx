import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { Alert, Typography, theme } from 'antd';
import { WarningOutlined } from '@ant-design/icons';
import ChatInterface from '../components/ChatInterface';
import { healthConsult } from '../services/api';

const { Text } = Typography;

const HealthConsult: React.FC = () => {
  const { token } = theme.useToken();
  const [searchParams] = useSearchParams();
  const initialSessionId = searchParams.get('s') || undefined;
  const initialShowHistory = searchParams.get('show') === 'sessions';

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Alert
        message="健康咨询免责声明"
        description={
          <div>
            <Text>本系统提供的健康建议仅供参考，不能替代专业医疗诊断和治疗。</Text>
            <br />
            <Text strong style={{ color: token.colorError }}>
              如果您有紧急健康问题，请立即拨打急救电话（120）或前往医院就诊。
            </Text>
          </div>
        }
        type="warning"
        showIcon
        icon={<WarningOutlined />}
        style={{ marginBottom: 16 }}
      />
      <div style={{ flex: 1 }}>
        <ChatInterface
          title="健康咨询"
          subtitle="智能健康咨询助手 - 仅供参考，不构成医疗建议"
          apiFunction={healthConsult}
          showSafetyWarning={true}
          autoBindKB={true}
          initialSessionId={initialSessionId}
          initialShowHistory={initialShowHistory}
          autoLoadLastSession={!initialSessionId}
          sessionType="health"
        />
      </div>
    </div>
  );
};

export default HealthConsult;
