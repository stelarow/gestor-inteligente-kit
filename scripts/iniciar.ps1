# Liga tudo: WhatsApp (bridge) + Central (IA e painel). Uso: .\scripts\iniciar.ps1
param([switch]$SemAbrirPainel)
$raiz = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$raiz\bridge\bridge.exe")) {
  Write-Host "Compilando a bridge do WhatsApp (só na 1ª vez)..."
  Push-Location "$raiz\bridge"; go build -o bridge.exe .; Pop-Location
}
$bridgeNoAr = $false
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:8080/health | Out-Null; $bridgeNoAr = $true } catch {}
if (-not $bridgeNoAr) {
  Write-Host "Abrindo a bridge. Na 1ª vez aparece um QR code: WhatsApp > Aparelhos conectados > Conectar."
  Start-Process -WorkingDirectory "$raiz\bridge" -FilePath "$raiz\bridge\bridge.exe"
}
$centralNoAr = $false
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:8791/health | Out-Null; $centralNoAr = $true } catch {}
if (-not $centralNoAr) {
  Start-Process -WorkingDirectory $raiz -FilePath "python" -ArgumentList "-X","utf8","nucleo\router.py"
  Start-Sleep 3
}
if (-not $SemAbrirPainel) { Start-Process "http://127.0.0.1:8791/" }
