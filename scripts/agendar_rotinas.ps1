# Deixa o sistema rodando sozinho no Agendador de Tarefas do Windows (Encontro 6).
# Uso:  powershell -File scripts\agendar_rotinas.ps1              (liga Central, grupo e notas)
#       powershell -File scripts\agendar_rotinas.ps1 -ComEnvio    (também chama de volta às 10h, de seg a sáb)
#       powershell -File scripts\agendar_rotinas.ps1 -Remover     (desliga tudo)
param([switch]$ComEnvio, [switch]$Remover, [int]$LimitePorDia = 20)

$raiz = Split-Path -Parent $PSScriptRoot
$py = (Get-Command python).Source
$nomes = "GI-Ligar-Tudo", "GI-Grupo-Equipe", "GI-Nota-Contatos", "GI-Chamar-De-Volta"

if ($Remover) {
  foreach ($n in $nomes) { Unregister-ScheduledTask -TaskName $n -Confirm:$false -ErrorAction SilentlyContinue }
  Write-Host "✅ Rotinas removidas."; exit
}

function Tarefa($nome, $argumentos, $gatilho) {
  $acao = New-ScheduledTaskAction -Execute $py -Argument "-X utf8 $argumentos" -WorkingDirectory $raiz
  $cfg = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
         -ExecutionTimeLimit (New-TimeSpan -Hours 0)
  Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $cfg -Force | Out-Null
  Write-Host "✅ $nome"
}

# Central + WhatsApp: ao entrar no Windows e conferindo a cada 5 minutos (religa se cair)
$acaoLigar = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$raiz\scripts\iniciar.ps1`" -SemAbrirPainel" -WorkingDirectory $raiz
$g1 = New-ScheduledTaskTrigger -AtLogOn
$g2 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "GI-Ligar-Tudo" -Action $acaoLigar -Trigger $g1, $g2 -Force | Out-Null
Write-Host "✅ GI-Ligar-Tudo"

Tarefa "GI-Grupo-Equipe" "nucleo\grupo_equipe.py" (New-ScheduledTaskTrigger -AtLogOn)
Tarefa "GI-Nota-Contatos" "nucleo\nota_contatos.py" (New-ScheduledTaskTrigger -Daily -At 8am)
if ($ComEnvio) {
  $g = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday, Saturday -At 10am
  Tarefa "GI-Chamar-De-Volta" "nucleo\chamar_de_volta.py --enviar --limite $LimitePorDia" $g
} else {
  Write-Host "ℹ️ Chamar de volta NÃO agendado (use -ComEnvio quando o líder aprovar as mensagens)."
}
