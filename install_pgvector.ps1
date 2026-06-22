# =============================================================================
# pgvector 扩展安装脚本（Windows PowerShell）
# 将预编译的 pgvector 文件复制到 PostgreSQL 18 安装目录中
# 以管理员身份运行此脚本
# =============================================================================

# 输出提示信息：开始复制 pgvector 文件
Write-Host "Copying pgvector files..." -ForegroundColor Yellow

# 复制扩展 SQL 定义文件（用于 CREATE EXTENSION vector; 命令）
# 源路径：项目中提取的 pgvector 扩展的 SQL 文件
# 目标路径：PostgreSQL 18 的扩展目录
Copy-Item -Path "C:\Users\swm_0\medagent\pgvector_extracted\share\extension\*" `
          -Destination "C:\Program Files\PostgreSQL\18\share\extension" `
          -Force -Recurse        # -Force：覆盖已存在的文件；-Recurse：递归复制所有子项

# 复制 pgvector 的动态链接库（DLL 文件）
# vector.dll 是 pgvector 扩展的核心二进制文件，提供向量数据类型和索引功能
Copy-Item -Path "C:\Users\swm_0\medagent\pgvector_extracted\lib\vector.dll" `
          -Destination "C:\Program Files\PostgreSQL\18\lib" `
          -Force

# 复制 C 语言头文件（PostgreSQL 扩展开发所需，供编译其他用到 vector 类型的扩展使用）
# 创建目标目录（如已存在则静默跳过）
New-Item -Path "C:\Program Files\PostgreSQL\18\include\server\extension\vector" `
         -ItemType Directory -Force | Out-Null
# 复制所有头文件到 PostgreSQL 的 include 目录
Copy-Item -Path "C:\Users\swm_0\medagent\pgvector_extracted\include\*" `
          -Destination "C:\Program Files\PostgreSQL\18\include" `
          -Force -Recurse

# 输出提示信息：文件复制完成，准备重启 PostgreSQL
Write-Host "Files copied! Restarting PostgreSQL..." -ForegroundColor Green

# 重启 PostgreSQL 18 服务（使新安装的扩展生效）
Restart-Service -Name postgresql-x64-18 -Force

# 输出完成提示
Write-Host "PostgreSQL restarted. pgvector installation complete!" -ForegroundColor Green
