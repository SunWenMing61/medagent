// 引入 React 及其核心 Hooks：useState（状态管理）、useEffect（副作用处理）、useMemo（性能优化-记忆化计算）
import React, { useState, useEffect, useMemo } from 'react';
// 引入 React Router DOM 的路由组件：BrowserRouter（浏览器路由）、Routes/Route（路由定义）、Navigate（重定向）、useNavigate（编程式导航）、useLocation（获取当前URL）、Outlet（子路由插槽）
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
  useNavigate,
  useLocation,
  Outlet,
} from 'react-router-dom';
// 引入 Ant Design 的布局和 UI 组件：Layout（页面框架）、Menu（侧边栏导航菜单）、Button（按钮）、Dropdown（下拉菜单）、Avatar（用户头像）、Space（间距容器）、Typography（排版文字）、Spin（加载动画）、theme（获取设计令牌）
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
// 引入 Ant Design 图标：Dashboard（仪表盘）、QuestionCircle（问答）、Heart（健康）、Database（知识库）、File（文档）、Setting（设置）、User（用户）、Team（团队）、Message（消息）、Tool（工具）、Logout（退出）、MenuFold/MenuUnfold（侧边栏折叠/展开）、SafetyCertificate（安全认证）、Sun/Moon（主题切换）、Picture（背景图片）
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
// 引入自定义的主题上下文 Hook，用于获取和切换主题模式（light/dark/auto）及背景设置
import { useThemeContext } from './contexts/ThemeContext';
// 引入主题设置弹窗组件，用于上传和管理背景图片
import ThemeSettings from './components/ThemeSettings';
// 引入 API 服务：api（axios 实例）和 getCurrentUser（获取当前登录用户信息）
import { api, getCurrentUser } from './services/api';

// 引入各个页面组件：登录页、注册页、工作台、通用问答、健康咨询、知识库管理、文档管理、管理概览、用户管理、反馈管理、系统配置
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
// SourceManagement 组件现已合并到 KBManagement 中，以两个标签页（Tab）的形式呈现，故不再单独引入

// 从 Ant Design Layout 中解构出 Header（顶部导航栏）、Sider（侧边栏）、Content（主内容区）三个布局部件
const { Header, Sider, Content } = Layout;
// 从 Typography 中解构出 Text 组件，用于渲染文本
const { Text } = Typography;

/**
 * 用户信息接口，对应后端返回的用户数据结构
 * @property id - 用户唯一标识
 * @property username - 用户名
 * @property email - 用户邮箱
 * @property role - 用户角色（user 普通用户 / admin 管理员）
 * @property status - 用户状态（可选，如 active/disabled）
 */
interface UserInfo {
  id: number;
  username: string;
  email: string;
  role: string;
  status?: string;
}

/**
 * 认证守卫组件：检查用户是否已登录
 * 若 localStorage 中没有 access_token，则重定向到 /login 登录页，并携带当前路径以便登录后跳回
 * @param children - 需要受保护的子组件
 */
function AuthGuard({ children }: { children: React.ReactNode }) {
  // 从 localStorage 读取 JWT 访问令牌
  const token = localStorage.getItem('access_token');
  // 获取当前路由位置信息，用于登录后重定向回来
  const location = useLocation();

  // 如果没有令牌，说明未登录，强制跳转到登录页面，并传递当前路径作为 state
  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // 已登录，正常渲染子组件
  return <>{children}</>;
}

/**
 * 管理员守卫组件：检查当前用户是否为管理员角色
 * 若角色不是 admin，则重定向到 /dashboard（普通用户工作台）
 * @param children - 需要管理员权限的子组件
 */
function AdminGuard({ children }: { children: React.ReactNode }) {
  // 从 localStorage 读取用户角色
  const role = localStorage.getItem('user_role');

  // 非管理员用户无权访问，跳转到工作台首页
  if (role !== 'admin') {
    return <Navigate to="/dashboard" replace />;
  }

  // 是管理员，正常渲染子组件
  return <>{children}</>;
}

/**
 * 应用主布局组件：包含侧边栏导航、顶部栏、内容区和主题背景
 * 该组件仅在用户已登录后渲染，通过 Outlet 展示嵌套子路由的内容
 */
function AppLayout() {
  // 侧边栏折叠状态：true=折叠（只显示图标），false=展开（显示文字+图标）
  const [collapsed, setCollapsed] = useState(false);
  // 当前登录用户信息，初始为 null，加载成功后更新
  const [currentUser, setCurrentUser] = useState<UserInfo | null>(null);
  // 页面加载状态：true 时显示全局加载中动画
  const [loading, setLoading] = useState(true);
  // 主题背景设置弹窗的可见状态
  const [themeSettingsVisible, setThemeSettingsVisible] = useState(false);
  // 编程式导航函数，用于路由跳转
  const navigate = useNavigate();
  // 当前路由位置信息，用于高亮对应菜单项
  const location = useLocation();
  // 从 ThemeContext 获取主题相关属性：mode（用户设定的模式）、resolvedMode（实际生效的模式）、setMode（切换模式函数）、activeBgDataUrl（当前背景图片的 dataURL）
  const { mode, resolvedMode, setMode, activeBgDataUrl } = useThemeContext();
  // 从 Ant Design 主题系统获取设计令牌：colorBgContainer（容器背景色）、borderRadiusLG（大圆角值）
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  /**
   * 组件挂载时：检查登录令牌，尝试获取当前用户信息
   * 若令牌有效且请求成功，更新用户状态；若令牌无效（401），清除本地存储并跳转到登录页
   * 依赖项为 navigate，当 navigate 变化时重新执行
   */
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      // 调用 API 获取当前用户信息
      getCurrentUser()
        .then((res: any) => {
          // 成功：保存用户信息和角色到 state 和 localStorage
          setCurrentUser(res);
          localStorage.setItem('user_role', res.role || 'user');
        })
        .catch(() => {
          // 失败（如令牌过期）：清除所有认证相关的本地存储
          localStorage.removeItem('access_token');
          localStorage.removeItem('user_role');
          localStorage.removeItem('user_id');
          localStorage.removeItem('username');
          // 跳转到登录页
          navigate('/login');
        })
        .finally(() => setLoading(false));  // 无论成功失败，结束加载状态
    } else {
      // 没有令牌，直接结束加载
      setLoading(false);
    }
  }, [navigate]);

  /**
   * 退出登录处理函数：清除本地存储中的认证信息，重置用户状态，跳转到登录页
   */
  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_role');
    localStorage.removeItem('user_id');
    localStorage.removeItem('username');
    setCurrentUser(null);
    navigate('/login');
  };

  /**
   * 用户下拉菜单的配置项：展示用户信息和退出登录按钮
   * 根据角色显示"管理员"或"用户"前缀
   */
  const userMenuItems = [
    {
      key: 'profile',
      label: `(${currentUser?.role === 'admin' ? '管理员' : '用户'}) ${currentUser?.username || ''}`,
      disabled: true,  // 个人信息项不可点击，仅展示
    },
    { type: 'divider' as const },  // 分隔线
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,  // 点击时执行退出操作
    },
  ];

  /**
   * 侧边栏菜单项配置：使用 useMemo 优化性能，仅在 currentUser 变化时重新计算
   * 普通用户看到：工作台、智能问答（通用问答+健康咨询）、知识库管理、文档管理
   * 管理员额外看到：系统管理（管理概览、用户管理、反馈管理、系统配置）
   */
  const menuItems = useMemo(() => {
    // 基础菜单项，所有用户可见
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

    // 如果当前用户是管理员，追加系统管理分组菜单
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

  /**
   * 根据当前路由路径获取选中的菜单 key
   * 用于高亮侧边栏中对应的菜单项
   */
  const getSelectedKey = () => {
    const path = location.pathname;
    // 逐一匹配各管理页面路径，确保精确高亮
    if (path.startsWith('/admin/dashboard')) return '/admin/dashboard';
    if (path.startsWith('/admin/users')) return '/admin/users';
    if (path.startsWith('/admin/feedback')) return '/admin/feedback';
    if (path.startsWith('/admin/config')) return '/admin/config';
    if (path.startsWith('/documents')) return '/documents';
    return path;  // 默认返回当前路径，Ant Design Menu 会自动匹配
  };

  /**
   * 获取默认展开的菜单分组 key（用于子菜单分组）
   * 如果当前在问答相关页面，展开"智能问答"分组；如果在管理页面，展开"系统管理"分组
   */
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

  // 如果正在加载用户信息，全屏居中显示加载动画
  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  // 判断是否有激活的背景图片：activeBgDataUrl 非空即为 true
  const isBgActive = !!activeBgDataUrl;
  // 背景图片上覆盖层的颜色（透明，仅作为占位）
  const bgOverlayColor = 'rgba(0, 0, 0, 0)';

  return (
    <>
      {/* ===== 全屏背景图片 + 半透明遮罩层 ===== */}
      {/* 当用户上传了背景图片时，渲染一个固定定位的 full-screen 背景层 */}
      {isBgActive && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundImage: `url(${activeBgDataUrl})`,  // 以 dataURL 作为背景图
          backgroundSize: 'cover',                      // 覆盖整个视口
          backgroundPosition: 'center',                 // 居中显示
          backgroundAttachment: 'fixed',                 // 滚动时背景固定
          zIndex: 0,                                    // 置于最底层
        }}>
          {/* 遮罩层：位于背景图之上，用于降低背景亮度，提高文字可读性 */}
          <div style={{
            position: 'absolute',
            top: 0, left: 0, right: 0, bottom: 0,
            background: bgOverlayColor,
          }} />
        </div>
      )}

      {/* ===== 主布局容器 ===== */}
      <Layout style={{
        minHeight: '100vh',    // 至少占满整个视口高度
        position: 'relative',  // 相对定位，作为子元素绝对定位的参考
        zIndex: 1,             // 位于背景图片之上
        background: 'transparent',  // 透明背景以露出背景图片
      }}>
        {/* ===== 侧边栏 ===== */}
        <Sider
          trigger={null}              // 不使用默认的折叠触发器，由顶部按钮控制
          collapsible                 // 允许折叠
          collapsed={collapsed}       // 折叠状态由 state 控制
          breakpoint="lg"             // 在大屏幕断点以下自动折叠
          style={{
            overflow: 'auto',         // 内容溢出时滚动
            height: '100vh',          // 全屏高度
            position: 'fixed',        // 固定定位，不随内容滚动
            left: 0,
            top: 0,
            bottom: 0,
            zIndex: 100,              // 高于顶部栏的 z-index
            // 如果使用自定义背景，侧边栏背景设为半透明
            ...(isBgActive ? { background: 'rgba(0,21,41,0.55)' } : {}),
          }}
        >
          {/* 侧边栏顶部品牌标识区域 */}
          <div
            style={{
              height: 64,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(255,255,255,0.1)',  // 轻微白色透明背景
              margin: 8,
              borderRadius: 8,
            }}
          >
            {/* 安全认证图标，作为品牌 Logo */}
            <SafetyCertificateOutlined style={{ fontSize: 24, color: '#fff', marginRight: collapsed ? 0 : 8 }} />
            {/* 侧边栏展开时显示品牌名称 MedAgent */}
            {!collapsed && (
              <Text strong style={{ color: '#fff', fontSize: 16, whiteSpace: 'nowrap' }}>
                MedAgent
              </Text>
            )}
          </div>
          {/* 导航菜单：dark 主题，内联模式，选中项由路由决定，默认展开由当前路径决定 */}
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[getSelectedKey()]}
            defaultOpenKeys={getOpenKeys()}
            items={menuItems}
            // 使用自定义背景时，菜单背景设为透明
            {...(isBgActive ? { style: { background: 'transparent' } } : {})}
            onClick={({ key }) => {
              // 点击菜单项跳转到对应路由（排除分组项 qa-group 和 admin-group）
              if (key !== 'qa-group' && key !== 'admin-group') {
                navigate(key);
              }
            }}
          />
        </Sider>

        {/* ===== 右侧内容区域 ===== */}
        <Layout style={{
          marginLeft: collapsed ? 80 : 200,  // 根据侧边栏折叠状态调整左边距
          transition: 'margin-left 0.2s',    // 展开/折叠时平滑动画过渡
          background: 'transparent',          // 透明背景以露出背景图片
        }}>
          {/* ===== 顶部栏 ===== */}
          <Header
            style={{
              padding: '0 24px',
              // 根据是否使用自定义背景及主题模式，设置不同的背景色
              background: isBgActive
                ? (resolvedMode === 'dark' ? 'rgba(0,0,0,0.45)' : 'rgba(255,255,255,0.75)')
                : colorBgContainer,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',  // 左右两端布局：左边折叠按钮，右边主题切换+用户菜单
              boxShadow: isBgActive ? 'none' : '0 1px 4px rgba(0,0,0,0.08)',
              position: 'sticky',  // 粘性定位，滚动时保持固定在顶部
              top: 0,
              zIndex: 99,
            }}
          >
            {/* 侧边栏折叠/展开切换按钮 */}
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)}
            />
            {/* 右侧操作区域 */}
            <Space>
              {/* 主题模式切换下拉菜单：自动切换、浅色模式、深色模式、主题背景设置 */}
              <Dropdown
                menu={{
                  items: [
                    { key: 'auto', label: '自动切换', onClick: () => setMode('auto') },              // 根据时间自动切换
                    { key: 'light', icon: <SunOutlined />, label: '浅色模式', onClick: () => setMode('light') },
                    { key: 'dark', icon: <MoonOutlined />, label: '深色模式', onClick: () => setMode('dark') },
                    { type: 'divider' },
                    { key: 'theme-bg', icon: <PictureOutlined />, label: '主题背景', onClick: () => setThemeSettingsVisible(true) },
                  ],
                  selectedKeys: [mode],  // 高亮当前激活的模式
                }}
                placement="bottomRight"
              >
                {/* 触发按钮：根据当前实际模式显示太阳或月亮图标 */}
                <Button
                  type="text"
                  icon={resolvedMode === 'dark' ? <MoonOutlined style={{ fontSize: 18 }} /> : <SunOutlined style={{ fontSize: 18 }} />}
                />
              </Dropdown>
              {/* 用户信息下拉菜单 */}
              <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
                <Space style={{ cursor: 'pointer' }}>
                  {/* 用户头像，背景色使用 Ant Design 主色 #1677ff */}
                  <Avatar icon={<UserOutlined />} style={{ backgroundColor: '#1677ff' }} />
                  {/* 显示用户名，未获取到时显示"用户" */}
                  <Text>{currentUser?.username || '用户'}</Text>
                </Space>
              </Dropdown>
            </Space>
          </Header>

          {/* ===== 主内容区 ===== */}
          <Content
            style={{
              margin: 16,
              padding: 24,
              // 使用自定义背景时，内容区背景设为半透明；否则使用 Ant Design 的容器背景色
              background: isBgActive
                ? (resolvedMode === 'dark' ? 'rgba(0,0,0,0.55)' : 'rgba(255,255,255,0.80)')
                : colorBgContainer,
              borderRadius: borderRadiusLG,
              minHeight: 280,
            }}
          >
            {/* Outlet 渲染嵌套子路由的页面组件（由 Routes 中定义的嵌套 Route 决定） */}
            <Outlet />
          </Content>
        </Layout>

        {/* 主题背景设置弹窗组件 */}
        <ThemeSettings
          open={themeSettingsVisible}
          onClose={() => setThemeSettingsVisible(false)}
        />
      </Layout>
    </>
  );
}

/**
 * 应用根组件 App
 * 定义全局路由结构：
 * - /login、/register 为公开页面
 * - 其他路由被 AuthGuard 保护，必须登录才能访问
 * - /admin/* 路径额外受 AdminGuard 保护，仅管理员可访问
 * - 根路径 / 和未匹配路径 * 重定向到 /dashboard
 */
function App() {
  return (
    <Router>
      <Routes>
        {/* 公开路由：登录页 */}
        <Route path="/login" element={<Login />} />
        {/* 公开路由：注册页 */}
        <Route path="/register" element={<Register />} />
        {/* 受保护的路由组：先经过 AuthGuard 认证，再渲染 AppLayout 布局 */}
        <Route
          element={
            <AuthGuard>
              <AppLayout />
            </AuthGuard>
          }
        >
          {/* 嵌套在 AppLayout 中的子路由，通过 Outlet 渲染 */}
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/qa" element={<MedicalQA />} />
          <Route path="/health" element={<HealthConsult />} />
          <Route path="/kb" element={<KBManagement />} />
          {/* /sources 为兼容旧路径，重定向到 /kb 并切换到在线来源标签页 */}
          <Route path="/sources" element={<Navigate to="/kb?tab=online" replace />} />
          <Route path="/documents" element={<DocumentManagement />} />
          {/* 带知识库 ID 的文档管理路由，用于查看特定知识库的文档 */}
          <Route path="/documents/:kbId" element={<DocumentManagement />} />
          {/* 管理后台路由：额外受 AdminGuard 保护 */}
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
        {/* 根路径重定向到工作台 */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        {/* 未匹配路径也重定向到工作台（404 兜底） */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Router>
  );
}

// 默认导出 App 组件，供 index.tsx 挂载使用
export default App;
