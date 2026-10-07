param([Parameter(Mandatory=$true)][string]$ResultPath,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
if (Test-Path -LiteralPath $OutputPath) { throw 'Fresh output required' }
$hasher=[System.Security.Cryptography.SHA256]::Create()
try { $digest=[System.BitConverter]::ToString($hasher.ComputeHash([System.IO.File]::ReadAllBytes($ResultPath))).Replace('-','').ToLowerInvariant() }
finally { $hasher.Dispose() }
if ($digest -ne '1fc84dbce62ec26e7f4990273e9740132af25da11a111e4bff44500f3cd3d88d') { throw 'Aggregate pin differs' }
$report=Get-Content -LiteralPath $ResultPath -Raw | ConvertFrom-Json
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -Path 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.Windows.Forms.DataVisualization.dll'
$chart=New-Object System.Windows.Forms.DataVisualization.Charting.Chart
$chart.Width=1800; $chart.Height=1120; $chart.BackColor=[System.Drawing.Color]::White
$font=New-Object System.Drawing.Font('Arial',12)
$title=New-Object System.Windows.Forms.DataVisualization.Charting.Title
$title.Text='Do prompt-held-out scalar maps predict human ratings?'; $title.Font=New-Object System.Drawing.Font('Arial',22,[System.Drawing.FontStyle]::Bold)
$title.Position=New-Object System.Windows.Forms.DataVisualization.Charting.ElementPosition(0,0,100,5)
$chart.Titles.Add($title)
$subtitle=New-Object System.Windows.Forms.DataVisualization.Charting.Title
$subtitle.Text='Historical six-arm HANNA panels | blue circles: original n=6, g=6 | orange diamonds: later n=5, g=4'
$subtitle.Font=New-Object System.Drawing.Font('Arial',13)
$subtitle.Position=New-Object System.Windows.Forms.DataVisualization.Charting.ElementPosition(0,5,100,4)
$chart.Titles.Add($subtitle)
$arms=@('hbq_short_story_batch32','compact_analytic','holistic_anchored','cambridge_igcse_0500_p2_mj_2024','naplan_narrative_2022','oregon_narrative_2017')
$labels=@('HBQ','Compact analytic','Holistic anchored','Cambridge','NAPLAN','Oregon')
for($j=0;$j -lt 6;$j++) {
    $name='panel'+$j; $area=New-Object System.Windows.Forms.DataVisualization.Charting.ChartArea($name)
    $col=$j%3; $row=[math]::Floor($j/3)
    $area.Position=New-Object System.Windows.Forms.DataVisualization.Charting.ElementPosition((1+$col*33), (11+$row*39), 32, 36)
    $area.BackColor=[System.Drawing.Color]::White
    foreach($axis in @($area.AxisX,$area.AxisY)) {
        $axis.Minimum=1; $axis.Maximum=5; $axis.Interval=1
        $axis.TitleFont=$font; $axis.LabelStyle.Font=$font
        $axis.MajorGrid.LineColor=[System.Drawing.Color]::FromArgb(225,225,225)
        $axis.LineColor=[System.Drawing.Color]::Gray
    }
    $area.AxisX.Title='Mean held-out prediction (1-5)'; $area.AxisY.Title='Mean human overall (1-5)'
    $chart.ChartAreas.Add($area)
    $heading=New-Object System.Windows.Forms.DataVisualization.Charting.Title
    $heading.Text=$labels[$j]; $heading.Font=New-Object System.Drawing.Font('Arial',15,[System.Drawing.FontStyle]::Bold)
    $heading.Position=New-Object System.Windows.Forms.DataVisualization.Charting.ElementPosition((1+$col*33),(9+$row*39),32,3)
    $chart.Titles.Add($heading)
    $identity=New-Object System.Windows.Forms.DataVisualization.Charting.Series('identity'+$j)
    $identity.ChartArea=$name; $identity.ChartType='Line'; $identity.Color=[System.Drawing.Color]::DarkGray; $identity.BorderDashStyle='Dash'; $identity.BorderWidth=2; $identity.IsVisibleInLegend=$false
    [void]$identity.Points.AddXY(1,1); [void]$identity.Points.AddXY(5,5); $chart.Series.Add($identity)
    for($k=0;$k -lt 2;$k++) {
        $cohort=if($k -eq 0){'original_rubric_v1_0_0'}else{'v8_rubric_v1_2_1'}
        $selected=@($report.rows | Where-Object {$_.arm -eq $arms[$j] -and $_.cohort -eq $cohort})
        if($selected.Count -ne 1){throw 'Expected exactly one arm/cohort aggregate'}
        $series=New-Object System.Windows.Forms.DataVisualization.Charting.Series($name+'cohort'+$k)
        $series.ChartArea=$name; $series.ChartType='Point'; $series.MarkerSize=12; $series.IsVisibleInLegend=$false
        $series.Color=if($k -eq 0){[System.Drawing.Color]::FromArgb(20,92,160)}else{[System.Drawing.Color]::FromArgb(210,95,15)}
        $series.MarkerStyle=if($k -eq 0){'Circle'}else{'Diamond'}; $series.Font=New-Object System.Drawing.Font('Arial',10)
        foreach($bin in $selected[0].isotonic_prediction_curve) {
            if($bin.items -lt 2){throw 'Individual target prohibited'}
            $index=$series.Points.AddXY([double]$bin.predicted_mean,[double]$bin.human_mean)
            $series.Points[$index].Label='n'+$bin.items+'/g'+$bin.prompt_groups
            $series.Points[$index].LabelForeColor=$series.Color
        }
        $chart.Series.Add($series)
    }
}
$footer=New-Object System.Windows.Forms.DataVisualization.Charting.Title
$footer.Text="Prompt-balanced two-bin means; n=items, g=represented prompts. Grey dashed line: identity.`nTraining folds contain 3-5 items. Known development data; shared raters and overlapping fits. No CI or deployment claim.`nSource: result.json SHA256 1fc84dbc...3d88d | exact 60 folds / 66 held-out item-arm units | HANNA copyright 2022 dig-team (MIT)"
$footer.Font=New-Object System.Drawing.Font('Arial',12)
$footer.Position=New-Object System.Windows.Forms.DataVisualization.Charting.ElementPosition(0,89,100,10)
$chart.Titles.Add($footer)
try { $chart.SaveImage([System.IO.Path]::GetFullPath($OutputPath),[System.Windows.Forms.DataVisualization.Charting.ChartImageFormat]::Png) }
finally { $chart.Dispose(); $font.Dispose() }
Write-Output ('Saved '+[System.IO.Path]::GetFullPath($OutputPath))
