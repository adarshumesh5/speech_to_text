# Sets Grogu's taskbar jump list (Tasks: New recording / Open Dictionary /
# Settings) via the managed WPF JumpList API, which is reliable across
# Windows 10/11 builds — unlike raw ICustomDestinationList calls from some
# Python processes, which crash inside windows.storage.dll.
#
# The AppUserModelID must match the one Grogu sets at startup ("Grogu") so the
# .automaticDestinations-ms file binds to the right taskbar button.
#
# Usage: powershell -NoProfile -STA -File jumplist.ps1 -ExePath "C:\...\Grogu.exe"

param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath
)

$ErrorActionPreference = 'Stop'

try {
    Add-Type -AssemblyName PresentationFramework

    # Match the app's process AUMID so the jump list binds to its button.
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class Aumid {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    public static extern int SetCurrentProcessExplicitAppUserModelID([MarshalAs(UnmanagedType.LPWStr)] string AppID);
}
"@
    [Aumid]::SetCurrentProcessExplicitAppUserModelID('Grogu') | Out-Null

    $app = New-Object System.Windows.Application
    # GetJumpList returns null when none has been set yet — construct directly.
    $jl = New-Object System.Windows.Shell.JumpList
    $jl.ShowFrequentCategory = $false
    $jl.ShowRecentCategory = $false

    $tasks = @(
        @{ Title = 'New recording';     Arguments = '--dictate' },
        @{ Title = 'Open Dictionary';   Arguments = '--dictionary' },
        @{ Title = 'Settings';          Arguments = '--settings' }
    )
    foreach ($t in $tasks) {
        $jt = New-Object System.Windows.Shell.JumpTask
        $jt.Title = $t.Title
        $jt.Arguments = $t.Arguments
        $jt.ApplicationPath = $ExePath
        $jt.IconResourcePath = $ExePath
        $jt.IconResourceIndex = 0
        [void]$jl.JumpItems.Add($jt)
    }

    [System.Windows.Shell.JumpList]::SetJumpList($app, $jl)
    Write-Output 'JUMPLIST_OK'
} catch {
    Write-Output ('JUMPLIST_FAILED: ' + $_.Exception.Message)
    exit 1
}
