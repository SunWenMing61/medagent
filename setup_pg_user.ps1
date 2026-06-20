# Run this script as Administrator to fix PostgreSQL medagent user/database
# Right-click -> "Run with PowerShell" (以管理员身份运行)

$pgBin = "C:\Program Files\PostgreSQL\18\bin"
$env:Path = "$pgBin;$env:PATH"

Write-Host "Step 1: Restart PostgreSQL with new config..." -ForegroundColor Yellow
Restart-Service postgresql-x64-18
Start-Sleep -Seconds 3

Write-Host "Step 2: Creating user 'medagent'..." -ForegroundColor Yellow
& "$pgBin\createuser.exe" -U postgres -h 127.0.0.1 -W medagent
# When prompted, enter the postgres superuser password
# (default is usually empty or 'postgres')

Write-Host "Step 3: Setting password..." -ForegroundColor Yellow
& "$pgBin\psql.exe" -U postgres -h 127.0.0.1 -c "ALTER USER medagent WITH PASSWORD 'your-password-here';"

Write-Host "Step 4: Creating database..." -ForegroundColor Yellow
& "$pgBin\createdb.exe" -U postgres -h 127.0.0.1 -O medagent medagent

Write-Host "Step 5: Granting permissions..." -ForegroundColor Yellow
& "$pgBin\psql.exe" -U postgres -h 127.0.0.1 -d medagent -c "GRANT ALL ON SCHEMA public TO medagent;"

Write-Host "Done! medagent user and database created." -ForegroundColor Green
