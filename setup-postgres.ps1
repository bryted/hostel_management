# setup-postgres.ps1 (non-interactive)
$pgPassPlain = "password"

# 1) Install PostgreSQL (latest)
winget install -e --id PostgreSQL.PostgreSQL

# 2) Create database
$env:PGPASSWORD = $pgPassPlain
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE hostel_management;"

# 3) Create .env
@"
DATABASE_URL=postgresql+psycopg://postgres:$pgPassPlain@localhost:5432/hostel_management
NOTIFICATIONS_MOCK=1
"@ | Set-Content -Encoding ASCII .env

Write-Host "Done. Now run: alembic upgrade head"
