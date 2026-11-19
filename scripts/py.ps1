# Ejecuta Python del venv compartido (python-browser). Uso: .\scripts\py.ps1 -m p03.cli seed
# Si existe .env propio o la clave ya esta en el entorno, no se toca. La clave de Groq se lee del .env de viralclip-pro
# SOLO en memoria (variable de entorno del proceso hijo); no se escribe en ningun archivo ni log.
param([Parameter(ValueFromRemainingArguments = $true)] $Rest)
$py = "D:\ClaudeBrain\apps\python-browser\Scripts\python.exe"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONUTF8 = "1"
if (-not $env:GROQ_API_KEY) {
  $envf = "D:\ClaudeBrain\proyectos\viralclip-pro\.env"
  if (Test-Path $envf) {
    $line = Get-Content $envf | Where-Object { $_ -match '^GROQ_API_KEY=' } | Select-Object -First 1
    if ($line) { $env:GROQ_API_KEY = ($line -replace '^GROQ_API_KEY=', '').Trim().Trim('"').Trim("'") }
  }
}
& $py @Rest
exit $LASTEXITCODE
