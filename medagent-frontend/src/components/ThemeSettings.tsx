// 引入 React 及其 useState Hook，用于管理上传状态
import React, { useState } from 'react';
// 引入 Ant Design 组件：Modal（弹窗）、Button（按钮）、Upload（上传组件）、Space（间距）、Typography（排版文字）、message（全局提示）、Empty（空状态）、Tooltip（工具提示）、Popconfirm（二次确认弹窗）
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
// 引入 Ant Design 图标：Upload（上传）、Delete（删除）、Picture（图片）、Check（选中勾号）
import {
  UploadOutlined,
  DeleteOutlined,
  PictureOutlined,
  CheckOutlined,
} from '@ant-design/icons';
// 引入自定义主题上下文 Hook 和背景图片类型
import { useThemeContext, type BgImageItem } from '../contexts/ThemeContext';

// 从 Typography 中解构出 Text 组件
const { Text } = Typography;

/**
 * 压缩图片至指定尺寸并转换为 base64 dataURL
 * 将图片缩放到最大宽 1920px、最大高 1080px（保持宽高比），然后以 JPEG 格式 85% 质量输出
 * 用于在浏览器端压缩用户上传的图片后存入 localStorage，节省存储空间
 * @param file - 用户选择的图片文件
 * @returns Promise 解析为 base64 编码的 dataURL 字符串
 */
function compressImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    // 第一步：将文件读取为 dataURL
    const reader = new FileReader();
    reader.onload = () => {
      // 第二步：创建 Image 对象加载图片
      const img = new Image();
      img.onload = () => {
        // 第三步：计算缩放后的尺寸，限制最大宽高
        const MAX_W = 1920;
        const MAX_H = 1080;
        let w = img.width;
        let h = img.height;
        // 等比缩放：如果宽度超出限制，按比例缩小宽度和高度
        if (w > MAX_W) { h = h * (MAX_W / w); w = MAX_W; }
        // 如果高度超出限制，按比例缩小高度和宽度
        if (h > MAX_H) { w = w * (MAX_H / h); h = MAX_H; }

        // 第四步：在 canvas 上绘制缩放后的图片并导出为 JPEG dataURL
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        if (!ctx) { reject(new Error('Canvas not supported')); return; }
        ctx.drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL('image/jpeg', 0.85));  // 0.85 为 JPEG 质量参数
      };
      img.onerror = () => reject(new Error('Image load failed'));
      img.src = reader.result as string;
    };
    reader.onerror = () => reject(new Error('File read failed'));
    reader.readAsDataURL(file);  // 开始读取文件
  });
}

/**
 * ThemeSettings 组件的 Props 接口
 * @property open - 弹窗是否可见
 * @property onClose - 关闭弹窗的回调函数
 */
interface ThemeSettingsProps {
  open: boolean;
  onClose: () => void;
}

/**
 * ThemeSettings 组件：主题背景设置弹窗
 * 功能：上传新的背景图片、查看已有背景列表、切换到某张背景、删除单张背景、清除所有背景
 * 图片保存在浏览器 localStorage 中（仅本地生效）
 */
const ThemeSettings: React.FC<ThemeSettingsProps> = ({ open, onClose }) => {
  // 从主题上下文获取背景图片相关状态和方法
  const { bgImages, activeBgId, setBgImages, setActiveBgId } = useThemeContext();
  // 上传中的加载状态
  const [uploading, setUploading] = useState(false);

  /**
   * 处理图片上传：验证文件类型和大小，压缩后保存到列表
   * @param file - 用户选择的图片文件
   * @returns false 阻止 Upload 组件的默认上传行为
   */
  const handleUpload = async (file: File): Promise<boolean> => {
    // 验证是否为图片文件
    if (!file.type.startsWith('image/')) {
      antMessage.error('请选择图片文件');
      return false;
    }
    // 验证文件大小不超过 10MB
    if (file.size > 10 * 1024 * 1024) {
      antMessage.error('图片不能超过 10MB');
      return false;
    }
    setUploading(true);
    try {
      // 压缩图片为 base64 dataURL
      const dataUrl = await compressImage(file);
      // 提取文件名（去掉扩展名，截取前 20 字符）作为显示名称
      const ext = file.name.split('.').pop() || 'jpg';
      const baseName = file.name.replace(`.${ext}`, '').slice(0, 20);
      // 创建新的背景图片项，ID 使用时间戳+随机字符串确保唯一性
      const newItem: BgImageItem = {
        id: `bg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        name: baseName,
        dataUrl,
      };
      // 追加到列表并自动激活新上传的图片
      const updated = [...bgImages, newItem];
      setBgImages(updated);
      setActiveBgId(newItem.id);  // 上传后自动切换为新图片
      antMessage.success('主题背景已添加');
    } catch (err: any) {
      antMessage.error('图片处理失败: ' + err.message);
    } finally {
      setUploading(false);
    }
    return false;  // 阻止 Upload 的默认 HTTP 上传行为
  };

  /**
   * 删除单张背景图片
   * @param item - 要删除的图片项
   */
  const handleRemove = (item: BgImageItem) => {
    // 从列表中过滤掉该项
    const updated = bgImages.filter((i) => i.id !== item.id);
    setBgImages(updated);
    // 如果删除的是当前激活的图片，setBgImages 内部会自动处理激活 ID 的切换
    antMessage.success(`已删除「${item.name}」`);
  };

  /**
   * 清除所有背景图片
   */
  const handleClearAll = () => {
    setBgImages([]);
    setActiveBgId(null);
    antMessage.success('已清除所有背景');
  };

  return (
    <Modal
      title={<Space><PictureOutlined />主题背景设置</Space>}
      open={open}            // 弹窗可见状态
      onCancel={onClose}     // 点击遮罩或取消时关闭
      footer={null}          // 不使用默认底部按钮
      width={520}            // 弹窗宽度
      destroyOnClose         // 关闭时销毁内部组件状态
    >
      {/* 提示文字 */}
      <div style={{ marginBottom: 16 }}>
        <Text type="secondary">
          上传的图片会保存在浏览器中，点击即可切换为当前主题背景。
        </Text>
      </div>

      {/* 上传按钮区域 */}
      <div style={{ marginBottom: 20, textAlign: 'center' }}>
        {/* Ant Design Upload 组件：用于选择文件，beforeUpload 返回 false 阻止 HTTP 上传 */}
        <Upload
          accept="image/*"          // 仅接受图片类型文件
          showUploadList={false}    // 不显示文件列表
          beforeUpload={handleUpload}  // 上传前处理（压缩和保存）
          disabled={uploading}      // 上传中禁用
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

      {/* 背景图片网格展示区 */}
      {bgImages.length === 0 ? (
        // 无图片时的空状态
        <Empty
          image={<PictureOutlined style={{ fontSize: 48, color: '#d9d9d9' }} />}
          description="暂无背景图片，请上传"
        />
      ) : (
        // 使用 CSS Grid 网格布局展示所有背景图片缩略图
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',  // 自动填充列，每列最小 140px
          gap: 12,
        }}>
          {bgImages.map((item) => {
            const isActive = item.id === activeBgId;  // 判断是否为当前激活的背景
            return (
              <div
                key={item.id}
                style={{
                  position: 'relative',
                  borderRadius: 8,
                  overflow: 'hidden',
                  cursor: 'pointer',
                  border: isActive ? '3px solid #1677ff' : '2px solid #f0f0f0',  // 激活状态显示蓝色边框
                  aspectRatio: '16 / 9',     // 16:9 比例
                  transition: 'border-color 0.2s',
                }}
                onClick={() => {
                  // 点击切换为当前背景
                  setActiveBgId(item.id);
                  antMessage.success(`已切换到「${item.name}」`);
                }}
              >
                {/* 图片缩略图 */}
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
                {/* 激活状态的勾号标识（左上角蓝色圆形勾） */}
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
                {/* 删除按钮（右上角） */}
                <div
                  style={{
                    position: 'absolute',
                    top: 4,
                    right: 4,
                    opacity: 0.85,
                  }}
                  onClick={(e) => e.stopPropagation()}  // 阻止冒泡，防止触发图片切换
                >
                  <Popconfirm
                    title="删除背景"
                    description={`确定要删除「${item.name}」吗？`}
                    onConfirm={() => handleRemove(item)}
                    okText="删除"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}  // 确认按钮为危险样式
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
                {/* 图片名称标签（底部半透明黑底白字） */}
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

      {/* 清除所有背景按钮 */}
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

      {/* 底部统计信息 */}
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

// 默认导出 ThemeSettings 组件
export default ThemeSettings;
