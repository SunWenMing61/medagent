import React, { useState, useEffect, useMemo } from 'react';
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
  useNavigate,
  useLocation,
  Outlet,
} from 'react-router-dom';
import {
  Layout,
  Menu,
  Button,
  Dropdown,
  Avatar,
  Space,
  Typography,
  Spin,
  theme,
} from 'antd';
import {
  DashboardOutlined,
  QuestionCircleOutlined,
  HeartOutlined,
  DatabaseOutlined,
  FileOutlined,
  SettingOutlined,
  UserOutlined,
  TeamOutlined,
  MessageOutlined,
  ToolOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SafetyCertificateOutlined,
  SunOutlined,
  MoonOutlined,
  PictureOutlined,
} from '@ant-design/icons';
import { useThemeContext } from './contexts/ThemeContext';
import ThemeSettings from './components/ThemeSettings';
import { api, getCurrentUser } from './services/api';

import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import MedicalQA from './pages/MedicalQA';
import HealthConsult from './pages/HealthConsult';
import KBManagement from './pages/KBManagement';
import DocumentManagement from './pages/DocumentManagement';
import AdminDashboard from './pages/AdminDashboard';
import AdminUsers from './pages/AdminUsers';
import AdminFeedback from './pages/AdminFeedback';
import AdminConfig from './pages/AdminConfig';
// SourceManagement is now merged into KBManagement with two tabs

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

interface UserInfo {
  id: number;
  username: string;
  email: string;
  role: string;
  status?: string;
}

function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('access_token');
  const location = useLocation();

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

function AdminGuard({ children }: { children: React.ReactNode }) {
  const role = localStorage.getItem('user_role');

  if (role !== 'admin') {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}

function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [currentUser, setCurrentUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [themeSettingsVisible, setThemeSettingsVisible] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { mode, resolvedMode, setMode, activeBgDataUrl } = useThemeContext();
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      getCurrentUser()
        .then((res: any) => {
          setCurrentUser(res);
          localStorage.setItem('user_role', res.role || 'user');
        })
        .catch(() => {
          localStorage.removeItem('access_token');
          localStorage.removeItem('user_role');
          localStorage.removeItem('user_id');
          localStorage.removeItem('username');
          navigate('/login');
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_role');
    localStorage.removeItem('user_id');
    localStorage.removeItem('username');
    setCurrentUser(null);
    navigate('/login');
  };

  const userMenuItems = [
    {
      key: 'profile',
      label: `(${currentUser?.role === 'admin' ? '管理员' : '用户'}) ${currentUser?.username || ''}`,
      disabled: true,
    },
    { type: 'divider' as const },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
    },
  ];

  const menuItems = useMemo(() => {
    const items: any[] = [
      {
        key: '/dashboard',
        icon: <DashboardOutlined />,
        label: '工作台',
      },
      {
        key: 'qa-group',
        icon: <QuestionCircleOutlined />,
        label: '智能问答',
        children: [
          {
            key: '/qa',
            icon: <MessageOutlined />,
            label: '通用问答',
          },
          {
            key: '/health',
            icon: <HeartOutlined />,
            label: '健康咨询',
          },
        ],
      },
      {
        key: '/kb',
        icon: <DatabaseOutlined />,
        label: '知识库管理',
      },
      {
        key: '/documents',
        icon: <FileOutlined />,
        label: '文档管理',
      },
    ];

    if (currentUser?.role === 'admin') {
      items.push({
        key: 'admin-group',
        icon: <SettingOutlined />,
        label: '系统管理',
        children: [
          {
            key: '/admin/dashboard',
            icon: <DashboardOutlined />,
            label: '管理概览',
          },
          {
            key: '/admin/users',
            icon: <TeamOutlined />,
            label: '用户管理',
          },
          {
            key: '/admin/feedback',
            icon: <MessageOutlined />,
            label: '反馈管理',
          },
          {
            key: '/admin/config',
            icon: <ToolOutlined />,
            label: '系统配置',
          },
        ],
      });
    }

    return items;
  }, [currentUser]);

  const getSelectedKey = () => {
    const path = location.pathname;
    if (path.startsWith('/admin/dashboard')) return '/admin/dashboard';
    if (path.startsWith('/admin/users')) return '/admin/users';
    if (path.startsWith('/admin/feedback')) return '/admin/feedback';
    if (path.startsWith('/admin/config')) return '/admin/config';
    if (path.startsWith('/documents')) return '/documents';
    return path;
  };

  const getOpenKeys = () => {
    const path = location.pathname;
    if (path.startsWith('/qa') || path.startsWith('/health') || path.startsWith('/drug') || path.startsWith('/paper')) {
      return ['qa-group'];
    }
    if (path.startsWith('/admin')) {
      return ['admin-group'];
    }
    return [];
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  const isBgActive = !!activeBgDataUrl;
  const bgOverlayColor = 'rgba(0, 0, 0, 0)';

  return (
    <>
      {/* Full-screen background image + overlay veil */}
      {isBgActive && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundImage: `url(${activeBgDataUrl})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundAttachment: 'fixed',
          zIndex: 0,
        }}>
          <div style={{
            position: 'absolute',
            top: 0, left: 0, right: 0, bottom: 0,
            background: bgOverlayColor,
          }} />
        </div>
      )}

      <Layout style={{
        minHeight: '100vh',
        position: 'relative',
        zIndex: 1,
        background: 'transparent',
      }}>
        <Sider
          trigger={null}
          collapsible
          collapsed={collapsed}
          breakpoint="lg"
          style={{
            overflow: 'auto',
            height: '100vh',
            position: 'fixed',
            left: 0,
            top: 0,
            bottom: 0,
            zIndex: 100,
            ...(isBgActive ? { background: 'rgba(0,21,41,0.55)' } : {}),
          }}
        >
          <div
            style={{
              height: 64,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(255,255,255,0.1)',
              margin: 8,
              borderRadius: 8,
            }}
          >
            <SafetyCertificateOutlined style={{ fontSize: 24, color: '#fff', marginRight: collapsed ? 0 : 8 }} />
            {!collapsed && (
              <Text strong style={{ color: '#fff', fontSize: 16, whiteSpace: 'nowrap' }}>
                MedAgent
              </Text>
            )}
          </div>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[getSelectedKey()]}
            defaultOpenKeys={getOpenKeys()}
            items={menuItems}
            {...(isBgActive ? { style: { background: 'transparent' } } : {})}
            onClick={({ key }) => {
              if (key !== 'qa-group' && key !== 'admin-group') {
                navigate(key);
              }
            }}
          />
        </Sider>
        <Layout style={{
          marginLeft: collapsed ? 80 : 200,
          transition: 'margin-left 0.2s',
          background: 'transparent',
        }}>
          <Header
            style={{
              padding: '0 24px',
              background: isBgActive
                ? (resolvedMode === 'dark' ? 'rgba(0,0,0,0.45)' : 'rgba(255,255,255,0.75)')
                : colorBgContainer,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              boxShadow: isBgActive ? 'none' : '0 1px 4px rgba(0,0,0,0.08)',
              position: 'sticky',
              top: 0,
              zIndex: 99,
            }}
          >
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)}
            />
            <Space>
              <Dropdown
                menu={{
                  items: [
                    { key: 'auto', label: '自动切换', onClick: () => setMode('auto') },
                    { key: 'light', icon: <SunOutlined />, label: '浅色模式', onClick: () => setMode('light') },
                    { key: 'dark', icon: <MoonOutlined />, label: '深色模式', onClick: () => setMode('dark') },
                    { type: 'divider' },
                    { key: 'theme-bg', icon: <PictureOutlined />, label: '主题背景', onClick: () => setThemeSettingsVisible(true) },
                  ],
                  selectedKeys: [mode],
                }}
                placement="bottomRight"
              >
                <Button
                  type="text"
                  icon={resolvedMode === 'dark' ? <MoonOutlined style={{ fontSize: 18 }} /> : <SunOutlined style={{ fontSize: 18 }} />}
                />
              </Dropdown>
              <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
                <Space style={{ cursor: 'pointer' }}>
                  <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#1677ff' }} />
                  <Text>{currentUser?.username || '用户'}</Text>
                </Space>
              </Dropdown>
            </Space>
          </Header>
          <Content
            style={{
              margin: 16,
              padding: 24,
              background: isBgActive
                ? (resolvedMode === 'dark' ? 'rgba(0,0,0,0.55)' : 'rgba(255,255,255,0.80)')
                : colorBgContainer,
              borderRadius: borderRadiusLG,
              minHeight: 280,
            }}
          >
            <Outlet />
          </Content>
        </Layout>

        <ThemeSettings
          open={themeSettingsVisible}
          onClose={() => setThemeSettingsVisible(false)}
        />
      </Layout>
    </>
  );
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          element={
            <AuthGuard>
              <AppLayout />
            </AuthGuard>
          }
        >
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/qa" element={<MedicalQA />} />
          <Route path="/health" element={<HealthConsult />} />
          <Route path="/kb" element={<KBManagement />} />
          <Route path="/sources" element={<Navigate to="/kb?tab=online" replace />} />
          <Route path="/documents" element={<DocumentManagement />} />
          <Route path="/documents/:kbId" element={<DocumentManagement />} />
          <Route
            path="/admin/dashboard"
            element={
              <AdminGuard>
                <AdminDashboard />
              </AdminGuard>
            }
          />
          <Route
            path="/admin/users"
            element={
              <AdminGuard>
                <AdminUsers />
              </AdminGuard>
            }
          />
          <Route
            path="/admin/feedback"
            element={
              <AdminGuard>
                <AdminFeedback />
              </AdminGuard>
            }
          />
          <Route
            path="/admin/config"
            element={
              <AdminGuard>
                <AdminConfig />
              </AdminGuard>
            }
          />
        </Route>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Router>
  );
}

export default App;
