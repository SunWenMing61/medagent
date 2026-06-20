import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';

export type ThemeMode = 'light' | 'dark' | 'auto';

export interface BgImageItem {
  id: string;
  name: string;
  dataUrl: string;
}

interface ThemeContextValue {
  mode: ThemeMode;
  resolvedMode: 'light' | 'dark';
  setMode: (mode: ThemeMode) => void;
  toggle: () => void;
  bgImages: BgImageItem[];
  activeBgId: string | null;
  activeBgDataUrl: string | null;
  setBgImages: (images: BgImageItem[]) => void;
  setActiveBgId: (id: string | null) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  mode: 'auto',
  resolvedMode: 'light',
  setMode: () => {},
  toggle: () => {},
  bgImages: [],
  activeBgId: null,
  activeBgDataUrl: null,
  setBgImages: () => {},
  setActiveBgId: () => {},
});

export const useThemeContext = () => useContext(ThemeContext);

function getInitialMode(): ThemeMode {
  try {
    const stored = localStorage.getItem('theme_mode');
    if (stored === 'light' || stored === 'dark' || stored === 'auto') return stored;
  } catch { /* ignore */ }
  return 'auto';
}

function resolveMode(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'light') return 'light';
  if (mode === 'dark') return 'dark';
  const hour = new Date().getHours();
  return hour >= 19 || hour < 6 ? 'dark' : 'light';
}

const BG_IMAGES_KEY = 'theme_bg_images';
const BG_ACTIVE_KEY = 'theme_bg_active';
const BG_LEGACY_KEY = 'theme_bg_image';

function getInitialBgImages(): BgImageItem[] {
  try {
    // Check for legacy single image first
    const legacy = localStorage.getItem(BG_LEGACY_KEY);
    const stored = localStorage.getItem(BG_IMAGES_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
    if (legacy) {
      const items: BgImageItem[] = [{ id: 'bg-1', name: '背景 1', dataUrl: legacy }];
      localStorage.setItem(BG_IMAGES_KEY, JSON.stringify(items));
      localStorage.removeItem(BG_LEGACY_KEY);
      return items;
    }
  } catch { /* ignore */ }
  return [];
}

function getInitialActiveId(images: BgImageItem[]): string | null {
  try {
    const stored = localStorage.getItem(BG_ACTIVE_KEY);
    if (stored && images.some((i) => i.id === stored)) return stored;
  } catch { /* ignore */ }
  return images.length > 0 ? images[0].id : null;
}

function persistImages(images: BgImageItem[]) {
  try {
    localStorage.setItem(BG_IMAGES_KEY, JSON.stringify(images));
  } catch (e) {
    // localStorage full — remove the last image and retry
    if (images.length > 1) {
      const trimmed = images.slice(0, -1);
      try {
        localStorage.setItem(BG_IMAGES_KEY, JSON.stringify(trimmed));
      } catch { /* ignore */ }
    }
  }
}

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mode, setModeState] = useState<ThemeMode>(getInitialMode);
  const [resolvedMode, setResolvedMode] = useState<'light' | 'dark'>(() => resolveMode(getInitialMode()));
  const [bgImages, setBgImagesState] = useState<BgImageItem[]>(() => getInitialBgImages());
  const [activeBgId, setActiveBgIdState] = useState<string | null>(() => {
    const images = getInitialBgImages();
    return getInitialActiveId(images);
  });
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const updateResolved = useCallback((m: ThemeMode) => {
    setResolvedMode(resolveMode(m));
  }, []);

  const setMode = useCallback((m: ThemeMode) => {
    setModeState(m);
    updateResolved(m);
    try {
      localStorage.setItem('theme_mode', m);
    } catch { /* ignore */ }
  }, [updateResolved]);

  const toggle = useCallback(() => {
    const next = mode === 'light' ? 'dark' : mode === 'dark' ? 'auto' : 'light';
    setMode(next);
  }, [mode, setMode]);

  const setBgImages = useCallback((images: BgImageItem[]) => {
    setBgImagesState(images);
    persistImages(images);
    // If active image was removed, reset active
    setActiveBgIdState((current) => {
      if (current && !images.some((i) => i.id === current)) {
        const newId = images.length > 0 ? images[0].id : null;
        try {
          if (newId) localStorage.setItem(BG_ACTIVE_KEY, newId);
          else localStorage.removeItem(BG_ACTIVE_KEY);
        } catch { /* ignore */ }
        return newId;
      }
      return current;
    });
  }, []);

  const setActiveBgId = useCallback((id: string | null) => {
    setActiveBgIdState(id);
    try {
      if (id) localStorage.setItem(BG_ACTIVE_KEY, id);
      else localStorage.removeItem(BG_ACTIVE_KEY);
    } catch { /* ignore */ }
  }, []);

  const activeBgDataUrl = activeBgId
    ? bgImages.find((i) => i.id === activeBgId)?.dataUrl ?? null
    : null;

  // Auto-check timer when in 'auto' mode
  useEffect(() => {
    if (mode !== 'auto') {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }
    const id = setInterval(() => {
      updateResolved('auto');
    }, 60000);
    intervalRef.current = id;
    return () => { clearInterval(id); };
  }, [mode, updateResolved]);

  // Re-check on visibility change (tab switch)
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        updateResolved(mode);
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [mode, updateResolved]);

  // Update <html> data attribute
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolvedMode);
  }, [resolvedMode]);

  return (
    <ThemeContext.Provider value={{
      mode, resolvedMode, setMode, toggle,
      bgImages, activeBgId, activeBgDataUrl,
      setBgImages, setActiveBgId,
    }}>
      <ConfigProvider
        locale={zhCN}
        theme={{
          algorithm: resolvedMode === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
          token: {
            colorPrimary: '#1677ff',
            borderRadius: 6,
          },
        }}
      >
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  );
};

export default ThemeContext;
