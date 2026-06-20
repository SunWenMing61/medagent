# Install pgvector to PostgreSQL 18
Write-Host "Copying pgvector files..." -ForegroundColor Yellow

# Copy extension SQL files
Copy-Item -Path "C:\Users\swm_0\medagent\pgvector_extracted\share\extension\*" `
          -Destination "C:\Program Files\PostgreSQL\18\share\extension" `
          -Force -Recurse

# Copy DLL
Copy-Item -Path "C:\Users\swm_0\medagent\pgvector_extracted\lib\vector.dll" `
          -Destination "C:\Program Files\PostgreSQL\18\lib" `
          -Force

# Copy header files
New-Item -Path "C:\Program Files\PostgreSQL\18\include\server\extension\vector" `
         -ItemType Directory -Force | Out-Null
Copy-Item -Path "C:\Users\swm_0\medagent\pgvector_extracted\include\*" `
          -Destination "C:\Program Files\PostgreSQL\18\include" `
          -Force -Recurse

Write-Host "Files copied! Restarting PostgreSQL..." -ForegroundColor Green

# Restart PostgreSQL
Restart-Service -Name postgresql-x64-18 -Force

Write-Host "PostgreSQL restarted. pgvector installation complete!" -ForegroundColor Green
