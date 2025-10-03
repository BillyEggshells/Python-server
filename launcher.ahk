^!q:: {  ; Ctrl+Alt+Q
    ; Path to 32-bit PowerShell
    psPath := "C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"

    ; PowerShell commands:
    ; 1) Change directory
    ; 2) Run Python script
    psArgs := "-NoExit -ExecutionPolicy Bypass -Command & { Set-Location 'C:\Users\290344\Desktop'; python server.py --terminal }"

    ; Launch PowerShell
    Run psPath . " " . psArgs

    ; Optional: tooltip confirmation
    Tooltip "Running serv.py in 32-bit PowerShell..." , 10, 10
    Sleep 1200
    Tooltip
}
