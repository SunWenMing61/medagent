Set UAC = CreateObject("Shell.Application")
UAC.ShellExecute "cmd.exe", "/c net stop postgresql-x64-18 & net start postgresql-x64-18", "", "runas", 1
