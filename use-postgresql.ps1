# Run from the TripWise project folder using: . .\use-postgresql.ps1
# Dot-sourcing keeps the connection variables in this terminal only.
$env:PGHOST = Read-Host "PostgreSQL host (usually 127.0.0.1)"
if (-not $env:PGHOST) { $env:PGHOST = "127.0.0.1" }
$env:PGPORT = Read-Host "Port (Enter for 5432)"
if (-not $env:PGPORT) { $env:PGPORT = "5432" }
$env:PGDATABASE = Read-Host "Database name (for example tripwise)"
$env:PGUSER = Read-Host "Database user"
$tripwisePassword = Read-Host "Database password" -AsSecureString
$env:PGPASSWORD = [System.Net.NetworkCredential]::new("", $tripwisePassword).Password
Remove-Variable tripwisePassword
$env:PGSSLMODE = Read-Host "SSL mode (Enter for prefer locally; require for hosted database)"
if (-not $env:PGSSLMODE) { $env:PGSSLMODE = "prefer" }
$env:DJANGO_SETTINGS_MODULE = "travel_planner.settings_postgresql"
Write-Host "This terminal now uses PostgreSQL. Run migrations before starting Django."
