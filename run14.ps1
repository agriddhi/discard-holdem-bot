param([string]$Prefix = "logs_rr")
$seeds = @(111, 222, 5, 7, 8, 9, 10, 11, 12, 13, 14, 17, 605522686)
$total = 0
foreach ($s in $seeds) {
    $out = py -3.11 engine.py bot.py example_bots\value_bot.py --seed $s --log-dir "$Prefix$s" | Out-String
    $line = ($out -split "`n") | Where-Object { $_ -like "*bot.py*net*" } | Select-Object -First 1
    $net = 0
    if ($line -match 'net\s+(-?\d+)') { $net = [int]$Matches[1] }
    $total += $net
    Write-Output ("seed {0,10}: {1,6}   running total {2}" -f $s, $net, $total)
}
# seed 333: reversed order (bot sits seat B)
$out = py -3.11 engine.py example_bots\value_bot.py bot.py --seed 333 --log-dir "${Prefix}333" | Out-String
$line = ($out -split "`n") | Where-Object { $_ -like "*bot.py*net*" } | Select-Object -First 1
$net = 0
if ($line -match 'net\s+(-?\d+)') { $net = [int]$Matches[1] }
$total += $net
Write-Output ("seed {0,10}: {1,6}   running total {2}" -f 333, $net, $total)
Write-Output "GRAND TOTAL: $total   (baseline +10040)"
