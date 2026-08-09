param(
    [Parameter(Mandatory = $true)][string]$In,
    [Parameter(Mandatory = $true)][string]$Out,
    [Parameter(Mandatory = $true)][int]$Format
)
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($In, $false, $true)
    $doc.SaveAs2($Out, $Format)
    $doc.Close(0)
    Write-Output "OK"
} finally {
    $word.Quit()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word)
}
