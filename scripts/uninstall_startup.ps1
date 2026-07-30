# Removes the shortcuts created by install_startup.ps1 (app files untouched).

foreach ($target in @(
    (Join-Path ([Environment]::GetFolderPath("Startup")) "Kannada Lookup.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop"))  "Kannada Lookup.lnk")
)) {
    if (Test-Path $target) {
        Remove-Item $target -Force
        Write-Host "Removed: $target"
    } else {
        Write-Host "Not present: $target"
    }
}
