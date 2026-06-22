# =============================================================================
# PostgreSQL medagent 用户/数据库安装脚本（Windows PowerShell）
# 以管理员身份运行：右键 -> "Run with PowerShell"（以管理员身份运行）
# 该脚本用于初始化 medagent 项目的 PostgreSQL 用户和数据库
# =============================================================================

# PostgreSQL 18 的 bin 目录路径（包含 psql.exe、createuser.exe、createdb.exe 等工具）
$pgBin = "C:\Program Files\PostgreSQL\18\bin"
# 将 PostgreSQL bin 目录添加到系统 PATH 环境变量中，以便直接调用命令
$env:Path = "$pgBin;$env:PATH"

# 步骤 1：重启 PostgreSQL 服务以确保新配置生效
Write-Host "Step 1: Restart PostgreSQL with new config..." -ForegroundColor Yellow
Restart-Service postgresql-x64-18
# 等待 3 秒，确保服务完全启动后再执行后续操作
Start-Sleep -Seconds 3

# 步骤 2：创建名为 'medagent' 的数据库用户
Write-Host "Step 2: Creating user 'medagent'..." -ForegroundColor Yellow
# 使用 createuser.exe 工具创建用户
# -U postgres  —— 以 postgres 超级用户身份连接
# -h 127.0.0.1 —— 通过 TCP 连接本地 PostgreSQL（而非 Unix socket）
# -W          —— 提示输入密码
& "$pgBin\createuser.exe" -U postgres -h 127.0.0.1 -W medagent
# 注意：执行时会提示输入 postgres 超级用户的密码
#（默认密码通常为空或为 'postgres'）

# 步骤 3：为 medagent 用户设置密码
Write-Host "Step 3: Setting password..." -ForegroundColor Yellow
# 使用 psql 执行 ALTER USER 命令设置密码
# 请将 'your-password-here' 替换为实际的强密码（需与 .env 文件中的密码一致）
& "$pgBin\psql.exe" -U postgres -h 127.0.0.1 -c "ALTER USER medagent WITH PASSWORD 'your-password-here';"

# 步骤 4：创建 medagent 数据库并指定 medagent 用户为所有者
Write-Host "Step 4: Creating database..." -ForegroundColor Yellow
# -U postgres    —— 以 postgres 用户连接
# -h 127.0.0.1   —— 通过 TCP 连接
# -O medagent    —— 设置数据库所有者为 medagent 用户
# 最后的 medagent 参数为数据库名称
& "$pgBin\createdb.exe" -U postgres -h 127.0.0.1 -O medagent medagent

# 步骤 5：授予 medagent 用户访问权限
Write-Host "Step 5: Granting permissions..." -ForegroundColor Yellow
# 连接到 medagent 数据库，将 public schema 的所有权限授予 medagent 用户
# 这样 medagent 用户可以创建/修改表、索引等数据库对象
& "$pgBin\psql.exe" -U postgres -h 127.0.0.1 -d medagent -c "GRANT ALL ON SCHEMA public TO medagent;"

# 完成提示
Write-Host "Done! medagent user and database created." -ForegroundColor Green
