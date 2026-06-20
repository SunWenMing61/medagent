import React, { useState } from 'react';
import {
  Modal,
  Button,
  Upload,
  Space,
  Typography,
  message as antMessage,
  Empty,
  Tooltip,
  Popconfirm,
} from 'antd';
import {
  UploadOutlined,
  DeleteOutlined,
  PictureOutlined,
  CheckOutlined,
} from '@ant-design/icons';
import { useThemeContext, type BgImageItem } from '../contexts/ThemeContext';

const { Text } = Typography;

/** Compress an image File to a base64 data URL (max 1920px wide, JPEG 85%) */
function compressImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const MAX_W = 1920;
        const MAX_H = 1080;
        let w = img.width;
        let h = img.height;
        if (w > MAX_W) { h = h * (MAX_W / w); w = MAX_W; }
        if (h > MAX_H) { w = w * (MAX_H / h); h = MAX_H; }

        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        if (!ctx) { reject(new Error('Canvas not supported')); return; }
        ctx.drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL('image/jpeg', 0.85));
      };
      img.onerror = () => reject(new Error('Image load failed'));
      img.src = reader.result as string;
    };
    reader.onerror = () => reject(new Error('File read failed'));
    reader.readAsDataURL(file);
  });
}

interface ThemeSettingsProps {
  open: boolean;
  onClose: () => void;
}

const ThemeSettings: React.FC<ThemeSettingsProps> = ({ open, onClose }) => {
  const { bgImages, activeBgId, setBgImages, setActiveBgId } = useThemeContext();
  const [uploading, setUploading] = useState(false);

  const handleUpload = async (file: File): Promise<boolean> => {
    if (!file.type.startsWith('image/')) {
      antMessage.error('请选择图片文件');
      return false;
    }
    if (file.size > 10 * 1024 * 1024) {
      antMessage.error('图片不能超过 10MB');
      return false;
    }
    setUploading(true);
    try {
      const dataUrl = await compressImage(file);
      const ext = file.name.split('.').pop() || 'jpg';
      const baseName = file.name.replace(`.${ext}`, '').slice(0, 20);
      const newItem: BgImageItem = {
        id: `bg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        name: baseName,
        dataUrl,
      };
      const updated = [...bgImages, newItem];
      setBgImages(updated);
      // Auto-activate the newly uploaded image
      setActiveBgId(newItem.id);
      antMessage.success('主题背景已添加');
    } catch (err: any) {
      antMessage.error('图片处理失败: ' + err.message);
    } finally {
      setUploading(false);
    }
    return false;
  };

  const handleRemove = (item: BgImageItem) => {
    const updated = bgImages.filter((i) => i.id !== item.id);
    setBgImages(updated);
    if (activeBgId === item.id) {
      // active was removed — setActiveBgId handles fallback in setBgImages
    }
    antMessage.success(`已删除「${item.name}」`);
  };

  const handleClearAll = () => {
    setBgImages([]);
    setActiveBgId(null);
    antMessage.success('已清除所有背景');
  };

  return (
    <Modal
      title={<Space><PictureOutlined />主题背景设置</Space>}
      open={open}
      onCancel={onClose}
      footer={null}
      width={520}
      destroyOnClose
    >
      <div style={{ marginBottom: 16 }}>
        <Text type="secondary">
          上传的图片会保存在浏览器中，点击即可切换为当前主题背景。
        </Text>
      </div>

      {/* Upload button */}
      <div style={{ marginBottom: 20, textAlign: 'center' }}>
        <Upload
          accept="image/*"
          showUploadList={false}
          beforeUpload={handleUpload}
          disabled={uploading}
        >
          <Button
            type="primary"
            icon={<UploadOutlined />}
            loading={uploading}
            size="large"
          >
            上传新背景
          </Button>
        </Upload>
      </div>

      {/* Image gallery */}
      {bgImages.length === 0 ? (
        <Empty
          image={<PictureOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />}
          description="暂无背景图片，请上传"
        />
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
          gap: 12,
        }}>
          {bgImages.map((item) => {
            const isActive = item.id === activeBgId;
            return (
              <div
                key={item.id}
                style={{
                  position: 'relative',
                  borderRadius: 8,
                  overflow: 'hidden',
                  cursor: 'pointer',
                  border: isActive ? '3px solid #1677ff' : '2px solid #f0f0f0',
                  aspectRatio: '16 / 9',
                  transition: 'border-color 0.2s',
                }}
                onClick={() => {
                  setActiveBgId(item.id);
                  antMessage.success(`已切换到「${item.name}」`);
                }}
              >
                <img
                  src={item.dataUrl}
                  alt={item.name}
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    display: 'block',
                  }}
                />
                {/* Active badge */}
                {isActive && (
                  <div style={{
                    position: 'absolute',
                    top: 4,
                    left: 4,
                    background: '#1677ff',
                    borderRadius: '50%',
                    width: 22,
                    height: 22,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    <CheckOutlined style={{ color: '#fff', fontSize: 12 }} />
                  </div>
                )}
                {/* Delete button */}
                <div
                  style={{
                    position: 'absolute',
                    top: 4,
                    right: 4,
                    opacity: 0.85,
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <Popconfirm
                    title="删除背景"
                    description={`确定要删除「${item.name}」吗？`}
                    onConfirm={() => handleRemove(item)}
                    okText="删除"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                  >
                    <Tooltip title="删除">
                      <Button
                        type="primary"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        style={{ width: 24, height: 24, minWidth: 24 }}
                      />
                    </Tooltip>
                  </Popconfirm>
                </div>
                {/* Image name */}
                <div style={{
                  position: 'absolute',
                  bottom: 0,
                  left: 0,
                  right: 0,
                  background: 'rgba(0,0,0,0.55)',
                  padding: '2px 6px',
                  fontSize: 11,
                  color: '#fff',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}>
                  {item.name}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Clear all */}
      {bgImages.length > 0 && (
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <Popconfirm
            title="清除所有背景"
            description="确定要删除所有背景图片吗？"
            onConfirm={handleClearAll}
            okText="确认清除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button danger icon={<DeleteOutlined />}>
              清除所有背景
            </Button>
          </Popconfirm>
        </div>
      )}

      {bgImages.length > 0 && (
        <div style={{ marginTop: 12, textAlign: 'center' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            共 {bgImages.length} 张背景 · 点击图片切换 · 图片仅保存在本地浏览器
          </Text>
        </div>
      )}
    </Modal>
  );
};

export default ThemeSettings;
