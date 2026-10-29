' 启动小凉桌面宠物（静默版，不弹 cmd 窗口）
' 双击即可运行。适合日常使用。
' 想查看日志用 start_xiaoliang.bat 代替。
Set objShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
Set root = fso.GetParentFolderName(WScript.ScriptFullName)

py = root & "\.venv\Scripts\python.exe"
main = root & "\main.py"

If Not fso.FileExists(py) Then
    MsgBox "找不到 venv Python:" & vbCrLf & py & vbCrLf & vbCrLf & _
           "请先创建 venv 并安装依赖：" & vbCrLf & _
           "  python -m venv .venv" & vbCrLf & _
           "  .venv\Scripts\python.exe -m pip install -r requirements.txt", _
           vbCritical, "小凉启动失败"
    WScript.Quit 1
End If

objShell.CurrentDirectory = root
objShell.Run """" & py & """ """ & main & """", 0, False
