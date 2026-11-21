# Confere se está tudo certo. Uso: .\scripts\conferir.ps1
$raiz = Split-Path -Parent $PSScriptRoot
function ok($t){ Write-Host "✅ $t" } ; function ruim($t){ Write-Host "🚨 $t" }
if (Get-Command python -ErrorAction SilentlyContinue) { ok "Python instalado" } else { ruim "Falta o Python (python.org)" }
if (Get-Command go -ErrorAction SilentlyContinue) { ok "Go instalado" } else { ruim "Falta o Go (go.dev) para compilar a bridge" }
if (Test-Path "$raiz\.env") { ok "Arquivo .env existe" } else { ruim "Falta o .env (copie de .env.example)" }
if (Get-Command opencode -ErrorAction SilentlyContinue) { ok "OpenCode instalado (respostas)" } else { ruim "Falta o OpenCode: npm i -g opencode-ai  e depois  opencode auth login" }
if ((Get-Command codex -ErrorAction SilentlyContinue) -or (Get-Command claude -ErrorAction SilentlyContinue)) { ok "Codex ou Claude Code instalado (tarefas)" } else { ruim "Falta o Codex ou o Claude Code (tarefas complexas)" }
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:8080/health | Out-Null; ok "WhatsApp (bridge) no ar" } catch { ruim "WhatsApp (bridge) desligado" }
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:8791/health | Out-Null; ok "Central no ar: http://127.0.0.1:8791/" } catch { ruim "Central desligada" }
python -X utf8 "$raiz\testes\test_basico.py"
