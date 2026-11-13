# Phase 6 final validation: rebuild submission, verify zip layout, run the
# README checklist matches end-to-end FROM THE ZIP (in a non-OneDrive temp
# dir to avoid sync churn), and assert timing / notices / stderr caps.
#
# Usage: powershell -ExecutionPolicy Bypass -File final_check.ps1
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
$fail = 0

function Assert([string]$name, [bool]$cond, [string]$extra = "") {
    if ($cond) { Write-Output "ok   $name" }
    else { $script:fail++; Write-Output "FAIL $name $extra" }
}

# ---- 1. build + zip ------------------------------------------------------
py -3.11 build_submission.py
Assert "build_submission" ($LASTEXITCODE -eq 0)
if (Test-Path submission.zip) { Remove-Item submission.zip -Force }
Compress-Archive -Path dist\bot.py -DestinationPath submission.zip
Add-Type -AssemblyName System.IO.Compression.FileSystem
$z = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path submission.zip))
$entries = @($z.Entries | ForEach-Object { $_.FullName })
$size = @($z.Entries | ForEach-Object { $_.Length })[0]
$z.Dispose()
Assert "zip single entry bot.py at root" ($entries.Count -eq 1 -and $entries[0] -eq "bot.py") ($entries -join ",")
Assert "zip bot.py <= 5MB (Rulebook 5.10)" ($size -le 5MB) "$size bytes"

# ---- 2. e2e in temp (no OneDrive sync there) -----------------------------
$td = "C:\Users\Gaupad\AppData\Local\Temp\opencode\poker_e2e"
if (Test-Path $td) { Remove-Item -Recurse -Force $td }
New-Item -ItemType Directory -Path $td | Out-Null
Copy-Item engine.py $td
Copy-Item equity.py $td        # example bots import it from the project root
Copy-Item example_bots -Recurse $td
Expand-Archive submission.zip -DestinationPath $td
Set-Location $td

function Run-Check([string]$label, [string[]]$engArgs, [int]$bankPerLeg) {
    $out = (& py -3.11 engine.py @engArgs) -join "`n"
    Write-Output "--- $label"
    ($out -split "`n") | Where-Object { $_ -match "net|Result|Capped" } | ForEach-Object { Write-Output $_ }
    Assert "$label completed (no forfeit)" ($out -notmatch "forfeit")
    Assert "$label notices 0" ($out -match "notices 0" -and $out -notmatch "notices [1-9]")
    # our time: first bot.py net line carries "time used X s (bank Y s per leg)"
    $m = [regex]::Match($out, "bot\.py\s+net\s+[+-]?\d+\s+time used\s+([\d.]+) s \(bank (\d+) s per leg\)")
    if ($m.Success) {
        $used = [double]$m.Groups[1].Value
        $bank = [int]$m.Groups[2].Value
        Assert "$label time within bank" ($used -le 2 * $bank) "used ${used}s bank ${bank}s/leg"
        Write-Output "     time used ${used}s of $($bank * 2)s total"
    } else {
        Assert "$label time parsed" $false "no time-used line"
    }
    # stderr caps + no crash traces (engine writes them into --log-dir)
    Get-ChildItem -Recurse *_stderr.txt | ForEach-Object {
        Assert "$label $($_.Name) < 64KB" ($_.Length -lt 65536) "$($_.Length)"
        $txt = Get-Content $_.FullName -Raw
        if ($txt -match "Traceback") { Assert "$label $($_.Name) no traceback" $false }
        if ($txt -match "STALL") { Write-Output "     note: STALL watchdog fired in $($_.Name) (shrunk n, no loss of reply)" }
    }
}

# README checklist: full S1 match vs random inside the time bank
Run-Check "S1-vs-random" @("bot.py", "example_bots\random_bot.py", "--seed", "111", "--log-dir", "e2e_s1") 30
# Stage 2 timing over 1000 hands vs the strongest example bot
Run-Check "S2-vs-value" @("bot.py", "example_bots\value_bot.py", "--stage", "2", "--seed", "111", "--log-dir", "e2e_s2") 75

Set-Location $here
Write-Output ""
if ($fail -eq 0) { Write-Output "PHASE 6: ALL PASS" } else { Write-Output "PHASE 6: $fail FAILURES" }
exit $fail
