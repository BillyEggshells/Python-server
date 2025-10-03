^s::  ; Ctrl + S
{
    psPath := "C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
    psArgs := "-NoExit -ExecutionPolicy Bypass -Command `"& { . $PROFILE; Set-Location 'C:\Users\290344\Desktop'; python server.py --terminal }`""

    Run(psPath . " " . psArgs)

    ToolTip("Running server.py in 32-bit PowerShell with your profile...", 10, 10)
    Sleep(1200)
    ToolTip()
}
