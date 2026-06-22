// 引入 React 及其核心 API：createContext（创建上下文）、useContext（消费上下文）、useState（状态管理）、useEffect（副作用处理）、useCallback（回调函数记忆化）、useRef（引用存储）
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
// 引入 Ant Design 的 ConfigProvider（配置全局主题）和 theme（内置主题算法：浅色/深色）
import { ConfigProvider, theme } from 'antd';
// 引入 Ant Design 的中文语言包，用于组件文案本地化
import zhCN from 'antd/locale/zh_CN';

// 主题模式类型：'light' 浅色、'dark' 深色、'auto' 根据时间自动切换
export type ThemeMode = 'light' | 'dark' | 'auto';

// 背景图片项接口：每条记录包含唯一标识 ID、显示名称、图片的 dataURL（base64 编码）
export interface BgImageItem {
  id: string;
  name: string;
  dataUrl: string;
}

// 主题上下文的值接口定义，规定了上下文中暴露的所有属性和方法
interface ThemeContextValue {
  mode: ThemeMode;                              // 用户当前选中的主题模式（light/dark/auto）
  resolvedMode: 'light' | 'dark';               // 实际生效的主题模式（auto 模式下根据时间解析后的结果）
  setMode: (mode: ThemeMode) => void;            // 设置主题模式的函数
  toggle: () => void;                           // 循环切换主题模式：light -> dark -> auto -> light
  bgImages: BgImageItem[];                      // 所有上传的背景图片列表
  activeBgId: string | null;                    // 当前激活的背景图片 ID
  activeBgDataUrl: string | null;               // 当前激活的背景图片 dataURL（便捷计算属性）
  setBgImages: (images: BgImageItem[]) => void;  // 设置背景图片列表的函数
  setActiveBgId: (id: string | null) => void;    // 设置当前激活背景图片 ID 的函数
}

// 创建 ThemeContext，并提供默认值（初始状态均为空/兜底值，实际由 ThemeProvider 覆盖）
const ThemeContext = createContext<ThemeContextValue>({
  mode: 'auto',
  resolvedMode: 'light',
  setMode: () => {},        // 空函数占位，ThemeProvider 会覆盖
  toggle: () => {},          // 空函数占位，ThemeProvider 会覆盖
  bgImages: [],
  activeBgId: null,
  activeBgDataUrl: null,
  setBgImages: () => {},    // 空函数占位
  setActiveBgId: () => {},  // 空函数占位
});

// 使用 useContext 封装的便捷 Hook，供子组件直接调用获取主题上下文
export const useThemeContext = () => useContext(ThemeContext);

/**
 * 从 localStorage 读取用户之前保存的主题模式偏好
 * 若存储值合法（light/dark/auto）则返回该值，否则默认返回 'auto'
 * @returns 存储的主题模式，或 'auto'
 */
function getInitialMode(): ThemeMode {
  try {
    const stored = localStorage.getItem('theme_mode');
    if (stored === 'light' || stored === 'dark' || stored === 'auto') return stored;
  } catch { /* 忽略 localStorage 访问异常（如隐私模式） */ }
  return 'auto';  // 默认自动模式
}

/**
 * 解析主题模式为具体值：light 返回 light，dark 返回 dark，auto 根据当前时间判断
 * 自动模式下：晚上 19:00 到次日早上 6:00 为深色模式，其余时间为浅色模式
 * @param mode - 用户设定的模式
 * @returns 实际应该使用的主题：'light' 或 'dark'
 */
function resolveMode(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'light') return 'light';
  if (mode === 'dark') return 'dark';
  // auto 模式：根据当前小时数判断
  const hour = new Date().getHours();
  return hour >= 19 || hour < 6 ? 'dark' : 'light';  // 19点到次日6点为深色
}

// localStorage 中存储背景图片列表的键名
const BG_IMAGES_KEY = 'theme_bg_images';
// localStorage 中存储当前激活背景图片 ID 的键名
const BG_ACTIVE_KEY = 'theme_bg_active';
// 旧版本中存储单张背景图片的键名（兼容迁移用）
const BG_LEGACY_KEY = 'theme_bg_image';

/**
 * 从 localStorage 获取初始背景图片列表
 * 优先读取新格式的图片列表（theme_bg_images），若不存在则尝试读取旧格式（theme_bg_image）并迁移
 * @returns 背景图片项数组，没有则返回空数组
 */
function getInitialBgImages(): BgImageItem[] {
  try {
    // 先检查旧版单张背景图片
    const legacy = localStorage.getItem(BG_LEGACY_KEY);
    const stored = localStorage.getItem(BG_IMAGES_KEY);
    if (stored) {
      // 新版格式存在，尝试解析 JSON 并验证为数组
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
    if (legacy) {
      // 仅旧版存在：将旧版单张图片封装为新版数组格式，并保存，然后删除旧版键
      const items: BgImageItem[] = [{ id: 'bg-1', name: '背景 1', dataUrl: legacy }];
      localStorage.setItem(BG_IMAGES_KEY, JSON.stringify(items));
      localStorage.removeItem(BG_LEGACY_KEY);
      return items;
    }
  } catch { /* 忽略解析错误 */ }
  return [];  // 没有任何背景图片
}

/**
 * 获取初始激活的背景图片 ID
 * 优先使用 localStorage 中保存的 active ID，若该 ID 在图片列表中有效则返回；
 * 否则默认返回第一张图片的 ID，没有图片时返回 null
 * @param images - 当前背景图片列表
 * @returns 激活的图片 ID 或 null
 */
function getInitialActiveId(images: BgImageItem[]): string | null {
  try {
    const stored = localStorage.getItem(BG_ACTIVE_KEY);
    if (stored && images.some((i) => i.id === stored)) return stored;  // 存储的 ID 有效
  } catch { /* 忽略 */ }
  return images.length > 0 ? images[0].id : null;  // 默认选第一张
}

/**
 * 将背景图片列表持久化到 localStorage
 * 若 localStorage 空间不足，则尝试依次移除最后一张图片直到写入成功
 * @param images - 要保存的图片列表
 */
function persistImages(images: BgImageItem[]) {
  try {
    localStorage.setItem(BG_IMAGES_KEY, JSON.stringify(images));
  } catch (e) {
    // localStorage 存储空间已满 — 移除最后一张图片并重试
    if (images.length > 1) {
      const trimmed = images.slice(0, -1);  // 移除最后一项
      try {
        localStorage.setItem(BG_IMAGES_KEY, JSON.stringify(trimmed));
      } catch { /* 仍然失败则放弃 */ }
    }
  }
}

/**
 * ThemeProvider 组件：包裹应用根节点，提供全局主题上下文
 * 管理主题模式（浅色/深色/自动）、背景图片的上传与切换
 * 自动模式（auto）下每分钟检查一次时间以决定实际主题
 * 标签页切换至可见时也会重新检查主题
 */
export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // 当前主题模式 state，初始值从 localStorage 读取
  const [mode, setModeState] = useState<ThemeMode>(getInitialMode);
  // 实际解析后的主题（light/dark），初始值根据模式计算
  const [resolvedMode, setResolvedMode] = useState<'light' | 'dark'>(() => resolveMode(getInitialMode()));
  // 背景图片列表 state，初始值从 localStorage 读取
  const [bgImages, setBgImagesState] = useState<BgImageItem[]>(() => getInitialBgImages());
  // 当前激活的背景图片 ID，初始值从 localStorage 读取
  const [activeBgId, setActiveBgIdState] = useState<string | null>(() => {
    const images = getInitialBgImages();
    return getInitialActiveId(images);
  });
  // 定时器引用，用于 auto 模式下每分钟检查时间
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /**
   * 根据主题模式更新实际的 resolvedMode
   * 使用 useCallback 记忆化以避免不必要的重新渲染
   */
  const updateResolved = useCallback((m: ThemeMode) => {
    setResolvedMode(resolveMode(m));
  }, []);

  /**
   * 设置主题模式：更新 state、重新解析实际主题、持久化到 localStorage
   */
  const setMode = useCallback((m: ThemeMode) => {
    setModeState(m);
    updateResolved(m);
    try {
      localStorage.setItem('theme_mode', m);  // 持久化用户偏好
    } catch { /* 忽略 */ }
  }, [updateResolved]);

  /**
   * 循环切换主题模式：light -> dark -> auto -> light
   */
  const toggle = useCallback(() => {
    const next = mode === 'light' ? 'dark' : mode === 'dark' ? 'auto' : 'light';
    setMode(next);
  }, [mode, setMode]);

  /**
   * 设置背景图片列表：更新 state、持久化到 localStorage
   * 如果当前激活的图片被移除了，自动切换到第一张或设为 null
   */
  const setBgImages = useCallback((images: BgImageItem[]) => {
    setBgImagesState(images);
    persistImages(images);
    // 如果当前激活的图片不在新列表中，自动重置激活 ID
    setActiveBgIdState((current) => {
      if (current && !images.some((i) => i.id === current)) {
        const newId = images.length > 0 ? images[0].id : null;
        try {
          if (newId) localStorage.setItem(BG_ACTIVE_KEY, newId);
          else localStorage.removeItem(BG_ACTIVE_KEY);
        } catch { /* 忽略 */ }
        return newId;
      }
      return current;  // 激活的图片仍在列表中，保持不变
    });
  }, []);

  /**
   * 设置当前激活的背景图片 ID：更新 state、持久化到 localStorage
   */
  const setActiveBgId = useCallback((id: string | null) => {
    setActiveBgIdState(id);
    try {
      if (id) localStorage.setItem(BG_ACTIVE_KEY, id);
      else localStorage.removeItem(BG_ACTIVE_KEY);
    } catch { /* 忽略 */ }
  }, []);

  // 计算当前激活背景图片的 dataURL：根据 activeBgId 在 bgImages 中查找
  const activeBgDataUrl = activeBgId
    ? bgImages.find((i) => i.id === activeBgId)?.dataUrl ?? null
    : null;

  // ===== 自动模式定时器 =====
  // 当模式为 auto 时，每分钟检查一次时间并更新 resolvedMode
  // 当模式切换为非 auto 时，清除定时器
  useEffect(() => {
    if (mode !== 'auto') {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }
    // auto 模式下设置每分钟执行的定时器
    const id = setInterval(() => {
      updateResolved('auto');  // 重新根据当前时间计算主题
    }, 60000);  // 60 秒间隔
    intervalRef.current = id;
    return () => { clearInterval(id); };  // 组件卸载时清除定时器
  }, [mode, updateResolved]);

  // ===== 标签页可见性变化监听 =====
  // 当用户切回此标签页时，重新检查主题（因为 auto 模式下时间可能已变化）
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        updateResolved(mode);  // 用户回到页面时重新解析主题
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [mode, updateResolved]);

  // ===== 更新 HTML 文档的 data-theme 属性 =====
  // 同步 resolvedMode 到 <html> 标签的 data-theme 属性，供全局 CSS 使用
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolvedMode);
  }, [resolvedMode]);

  // ===== 渲染：提供上下文值并包裹 ConfigProvider =====
  return (
    <ThemeContext.Provider value={{
      mode, resolvedMode, setMode, toggle,
      bgImages, activeBgId, activeBgDataUrl,
      setBgImages, setActiveBgId,
    }}>
      {/* Ant Design 的 ConfigProvider：配置中文语言和主题算法 */}
      <ConfigProvider
        locale={zhCN}  // 使用中文语言包
        theme={{
          // 根据实际主题模式选择算法：darkAlgorithm（深色）或 defaultAlgorithm（浅色）
          algorithm: resolvedMode === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
          token: {
            colorPrimary: '#1677ff',  // 全局主色：Ant Design 默认蓝色
            borderRadius: 6,          // 全局圆角大小
          },
        }}
      >
        {children}  {/* 渲染所有子组件 */}
      </ConfigProvider>
    </ThemeContext.Provider>
  );
};

// 默认导出 ThemeContext（支持直接消费，但推荐使用 useThemeContext Hook）
export default ThemeContext;
