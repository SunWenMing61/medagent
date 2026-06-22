' =============================================================================
' PostgreSQL 服务重启脚本（VBScript）
' 通过 UAC 提权以管理员身份停止并重新启动 PostgreSQL 18 服务
' 双击运行即可（会自动弹出 UAC 确认窗口）
' =============================================================================

' 创建 Shell.Application 对象，用于以管理员权限执行命令
Set UAC = CreateObject("Shell.Application")

' 通过 ShellExecute 以管理员身份（runas）运行 cmd.exe
' 参数说明：
'   "cmd.exe"         —— 要执行的程序
'   "/c ..."          —— cmd 的参数：/c 表示执行后关闭窗口
'   ""                —— 工作目录（默认）
'   "runas"           —— 以管理员身份运行（触发 UAC 提权提示）
'   1                 —— 窗口显示状态（1 = 正常显示窗口）
'
' 执行的命令：
'   net stop postgresql-x64-18   —— 停止 PostgreSQL 18 服务
'   &                            —— 命令连接符（前一个成功后执行下一个）
'   net start postgresql-x64-18  —— 启动 PostgreSQL 18 服务
UAC.ShellExecute "cmd.exe", "/c net stop postgresql-x64-18 & net start postgresql-x64-18", "", "runas", 1
