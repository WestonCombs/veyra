# Run once from an elevated PowerShell if other devices cannot reach the hub.
# Rules apply only on Private networks and only to the local subnet.
$ErrorActionPreference = 'Stop'
$taskRuleName = 'CancelGroupMics-LocalHub'
if (-not (Get-NetFirewallRule -Name $taskRuleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name $taskRuleName -DisplayName 'Cancel Group Mics - local devices' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8787,8788 -Profile Private -RemoteAddress LocalSubnet
}
Write-Host 'Local hub access enabled on Private networks, TCP 8787 and 8788.'
