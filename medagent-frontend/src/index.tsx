// 引入 React 核心库，用于构建组件和 JSX 语法
import React from 'react';
// 引入 ReactDOM 的客户端渲染 API（React 18+），用于将应用挂载到 DOM 节点上
import ReactDOM from 'react-dom/client';
// 引入主题上下文提供者，包裹整个应用以实现全局主题切换功能（浅色/深色/自动）
import { ThemeProvider } from './contexts/ThemeContext';
// 引入根组件 App，包含路由和页面布局的顶层定义
import App from './App';
import './styles/global.css';

// 使用 createRoot 创建 React 18 的并发模式根节点，替代旧的 ReactDOM.render
// 获取 index.html 中 id 为 "root" 的 DOM 元素作为挂载点，断言为 HTMLElement 类型
const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);

// 调用 root.render 将应用渲染到页面上
root.render(
  // React.StrictMode 是开发模式下的严格模式检查工具，会帮助检测潜在问题（如副作用执行两次）
  <React.StrictMode>
    {/* ThemeProvider 包裹 App，为所有子组件提供主题上下文（mode、背景图等） */}
    <ThemeProvider>
      {/* App 是应用根组件，内部包含路由配置和布局结构 */}
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
