# PDF 文本清洗与工具治理架构

## 处理链路

PDF 不再以“整份文档是否有文字”决定是否 OCR，而是逐页处理：

1. PyMuPDF 提取带坐标、字体、字号、粗斜体和阅读顺序的 span/block。
2. 页面分类器输出 `embedded_text/scanned/hybrid/table_heavy/complex_layout/empty/garbled` 及判定原因。
3. 扫描页进入 OCR；混合页合并原生文字和 OCR，并做相似块去重。OCR 前执行灰度、自动对比度、增强和中值去噪，同时限制 DPI 与像素总量。
4. 清洗器保留医学符号，保守修复断词与低置信 OCR 数值/单位，移除重复页眉页脚、水印和页码，恢复标题、列表、脚注与表格。每次修改保存原文、结果、规则和置信度。
5. 连续页表头一致时合并跨页表格；表格按表头和行保存，分块时重复表头。
6. Raw Block、Clean Block、Page、Table 和 Cleaning Action 写入 MySQL；parent/child Chunk 与向量写入 PostgreSQL/pgvector。
7. 默认不计算文档质量高低、不进入人工复核、也不阻断向量化；只要清洗后存在有效文本块，就直接生成向量并入库。

原始层永不被清洗层覆盖，因此任意 Clean Block 和 Chunk 都能回溯页码、坐标、来源 block、提取方式、OCR 置信度和清洗版本。

## 工具体系

所有工具必须先注册 `ToolDefinition`，声明版本、输入/输出模型、类别、风险、允许的 Agent、权限范围、超时、重试、单次运行调用上限、缓存 TTL 与降级工具。

`ToolExecutor` 是唯一执行入口，顺序为：

1. 服务端覆盖 `user_id/tenant_id/authorized_kb_ids/request_id`，不接受调用者伪造身份上下文。
2. Pydantic 严格校验业务输入。
3. Tool Policy 检查 Agent、scope、急症风险、联网开关、健康状态和预算。
4. 查询幂等缓存；执行超时、有限重试和熔断。
5. 统一返回 `success/no_result/partial/error/forbidden/timeout/cancelled`、标准错误和 usage。
6. 记录调用、策略决定、错误、延迟、缓存命中和健康状态。

当前核心工具包括本地知识库、PubMed、FDA 药品标签、MSD Manual、会话记忆、相邻文档上下文和结构化医学表格。候选工具先按意图做确定性筛选，最多暴露四个，并再次经过执行时策略校验。

## API 与前端

- `GET /api/admin/tools`：工具注册信息与健康状态。
- `POST /api/admin/tools/{name}/enabled?enabled=true|false`：管理员启停工具。

“文档管理”页面展示解析、清洗、分块和向量入库进度；“系统管理 → 工具治理”展示 P95、错误率、熔断状态、权限和执行策略。

## 配置与依赖

关键配置位于 `medagent-backend/.env.example`，包括页面分类、版式/表格分析、OCR DPI 与像素上限、分块大小、工具超时/缓存/熔断。`DOCUMENT_QUALITY_ASSESSMENT_ENABLED=false` 表示清洗后直接向量化。OCR 依赖分为：

- `requirements-ocr-cpu.txt`：CPU 部署。
- `requirements-ocr-gpu.txt`：GPU 部署，CUDA/PyTorch 版本需按运行环境选择。

数据库升级使用 Alembic revision `0005_pdf_tooling_v2`。部署前应先备份 MySQL/PostgreSQL，并在预发布环境分别执行两套数据库迁移。
