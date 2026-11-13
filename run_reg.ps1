$pat = '(?m)^\s*[AB]\s+bot\.py\s+net\s+([+-]?\d+)'
function Run-Match($name, $oppArgs, $logdir, $seed) {
    $cmd = @('-3.11', 'engine.py', 'bot.py') + $oppArgs + @('--seed', $seed, '--log-dir', $logdir)
    $out = (& py @cmd) -join "`n"
    $net = $null
    if ($out -match $pat) { $net = [int]$Matches[1] }
    $notice = if ($out -match 'notices\s+(\d+)') { $Matches[1] } else { '?' }
    $time = ''
    if ($out -match 'bot\.py\s+net\s+[+-]?\d+\s+time used\s+([\d.]+) s') { $time = $Matches[1] }
    Write-Output ("{0,-22} net {1,6}  notices {2}  time {3}s" -f $name, $net, $notice, $time)
}
Run-Match 'vs random S1'   @('example_bots\random_bot.py')        'logs_reg_rand' 111
Run-Match 'vs starter S1'  @('example_bots\starter_bot.py')        'logs_reg_st1'  111
Run-Match 'vs starter S2'  @('example_bots\starter_bot.py', '--stage', '2') 'logs_reg_st2' 111
Run-Match 'vs value_bot S2' @('example_bots\value_bot.py', '--stage', '2')  'logs_reg_val2' 111
Write-Output 'baseline: random +2267, starter S1 +1171, starter S2 +3372, value S2 +1680'
