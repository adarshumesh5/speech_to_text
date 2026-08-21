param([string]$Path = "dist\Grogu-0.5.0.msi")
$full = (Resolve-Path $Path).Path
$w = New-Object -ComObject WindowsInstaller.Installer
$db = $w.OpenDatabase($full, 0)
$view = $db.OpenView("SELECT Property, Value FROM Property")
$view.Execute()
do {
    $r = $view.Fetch()
    if ($r) {
        $name = $r.StringData(1)
        if ($name -eq "ProductName" -or $name -eq "ProductVersion" -or $name -eq "ProductCode") {
            Write-Output ("$name = " + $r.StringData(2))
        }
    }
} while ($r)
