// 引入 React 核心库
import React from 'react';
// 引入 React Router 的 useSearchParams Hook，用于读取 URL 查询参数
import { useSearchParams } from 'react-router-dom';
// 从 Ant Design 引入 Alert 警告提示组件、Typography 排版组件、theme 主题
import { Alert, Typography, theme } from 'antd';
// 引入警告图标（三角形感叹号），用于增强免责声明的视觉警示效果
import { WarningOutlined } from '@ant-design/icons';
// 引入通用聊天界面组件，提供问答对话 UI 交互
import ChatInterface from '../components/ChatInterface';
// 引入后端健康咨询 API 函数
import { healthConsult } from '../services/api';

// 从 Typography 中解构 Text 组件，用于渲染文本
const { Text } = Typography;

// 定义 HealthConsult（健康咨询）页面组件，类型为 React.FC
const HealthConsult: React.FC = () => {
  // 获取 Ant Design 主题 token，用于访问主题颜色变量（如错误色红色）
  const { token } = theme.useToken();
  // useSearchParams 获取 URL 查询参数对象
  const [searchParams] = useSearchParams();
  // 从 URL 参数 ?s=xxx 读取初始会话 ID；若无则为 undefined
  const initialSessionId = searchParams.get('s') || undefined;
  // 判断 ?show=sessions 是否为 true，决定是否初始显示历史会话列表
  const initialShowHistory = searchParams.get('show') === 'sessions';

  // 返回组件的 JSX 渲染内容
  return (
    // 最外层容器：撑满高度（100%），使用垂直弹性布局排列子元素
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* 免责声明警告条：固定在顶部，以醒目的方式提醒用户 */}
      <Alert
        // 警告标题
        message="健康咨询免责声明"
        // 警告详细描述内容
        description={
          <div>
            {/* 第一行提示：本系统仅作参考，不能替代专业医疗 */}
            <Text>本系统提供的健康建议仅供参考，不能替代专业医疗诊断和治疗。</Text>
            <br />
            {/* 第二行提示：紧急情况请拨打急救电话，使用加粗 + 红色强调 */}
            <Text strong style={{ color: token.colorError }}>
              如果您有紧急健康问题，请立即拨打急救电话（120）或前往医院就诊。
            </Text>
          </div>
        }
        // 警告类型为 warning（黄色警告样式）
        type="warning"
        // 显示图标（默认显示在标题左侧）
        showIcon
        // 自定义图标为警告三角形，突出警示效果
        icon={<WarningOutlined />}
        // 底部留 16px 间距与聊天界面区分
        style={{ marginBottom: 16 }}
      />
      {/* 聊天界面主体区域：flex:1 自动撑满剩余高度 */}
      <div style={{ flex: 1 }}>
        {/* 渲染通用聊天界面组件，传入健康咨询专属配置 */}
        <ChatInterface
          // 聊天标题：显示为 "健康咨询"
          title="健康咨询"
          // 副标题：提示用户仅供参考，不构成医疗建议
          subtitle="智能健康咨询助手 - 仅供参考，不构成医疗建议"
          // API 请求函数：用户发送消息时调用 healthConsult（后端健康咨询接口）
          apiFunction={healthConsult}
          // 开启安全警告模式：在界面上额外显示安全提示（区别于普通问答）
          showSafetyWarning={true}
          // 自动绑定知识库：健康咨询默认绑定医疗知识库，无需用户手动选择
          autoBindKB={true}
          // 从 URL 参数获取的初始会话 ID
          initialSessionId={initialSessionId}
          // 是否初始显示历史会话列表
          initialShowHistory={initialShowHistory}
          // 未指定会话 ID 时自动加载最近会话
          autoLoadLastSession={!initialSessionId}
          // 会话类型标记为 "health"，用于后端区分健康咨询和通用问答
          sessionType="health"
          defaultAssistantProfile="memory_qa"
        />
      </div>
    </div>
  );
};

// 导出 HealthConsult 组件供路由使用
export default HealthConsult;
