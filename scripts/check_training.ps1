# check_training.ps1 - Monitor background RL training for cop and thief
# Usage: .\scripts\check_training.ps1
# Logs are at D:\tmp\training_run\

$CopLogPath   = "D:\tmp\training_run\cop_train.log"
$CopErrPath   = "D:\tmp\training_run\cop_train.err"
$ThiefLogPath = "D:\tmp\training_run\thief_train.log"
$ThiefErrPath = "D:\tmp\training_run\thief_train.err"

Write-Host "=== COP TRAINING ===" -ForegroundColor Cyan
Get-Content $CopLogPath -Tail 5 -ErrorAction SilentlyContinue
Write-Host ""

Write-Host "=== THIEF TRAINING ===" -ForegroundColor Cyan
Get-Content $ThiefLogPath -Tail 5 -ErrorAction SilentlyContinue
Write-Host ""

Write-Host "=== ERRORS ===" -ForegroundColor Red
Get-Content $CopErrPath  -Tail 3 -ErrorAction SilentlyContinue
Get-Content $ThiefErrPath -Tail 3 -ErrorAction SilentlyContinue
Write-Host ""

Write-Host "=== PROCESS STATUS ===" -ForegroundColor Green
$procs = Get-WmiObject Win32_Process | Where-Object {
    $_.CommandLine -match "cop_worker.rl.train_recurrent|thief_worker.rl.train_recurrent"
}
foreach ($p in $procs) {
    $ps = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
    if ($ps) {
        Write-Host ("PID {0,6} | CPU {1,8:F1}s | RAM {2,6:F0}MB | {3}" -f `
            $ps.Id, $ps.CPU, ($ps.WorkingSet / 1MB), $p.CommandLine.Substring(0, [Math]::Min(80, $p.CommandLine.Length)))
    }
}

Write-Host ""
Write-Host "=== RECENT MODEL CHECKPOINTS ===" -ForegroundColor Magenta
Get-ChildItem D:\studies\AI_Agent_Orchestration_Course\submission_project\vibecode-cop\models\    -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 3 Name, LastWriteTime, Length
Get-ChildItem D:\studies\AI_Agent_Orchestration_Course\submission_project\vibecode-thief\models\  -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 3 Name, LastWriteTime, Length
