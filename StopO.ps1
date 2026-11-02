# StopO - para la grabacion de OBS y cierra OBS (pareja de StartO.ps1).
# Sin obs-websocket: pulsa el atajo "Detener grabacion" del perfil
# (Ctrl+Mayus+D), espera a que el log de OBS diga que la grabacion ha parado
# (fichero cerrado) y despues cierra OBS con WM_CLOSE, sin forzar nada.
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class Cierre {
    delegate bool EnumProc(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr p);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    // OBS sondea el teclado cada 25 ms: hay que mantener las teclas pulsadas.
    public static void CtrlMayusD() {
        byte[] teclas = { 0x11, 0x10, 0x44 };
        foreach (var k in teclas) keybd_event(k, 0, 0, UIntPtr.Zero);
        System.Threading.Thread.Sleep(150);
        Array.Reverse(teclas);
        foreach (var k in teclas) keybd_event(k, 0, 2, UIntPtr.Zero);
    }
    // OBS minimizado a la bandeja no tiene ventana visible: se avisa a todas las suyas.
    public static void Cerrar(int proceso) {
        EnumWindows((h, p) => {
            uint pid; GetWindowThreadProcessId(h, out pid);
            if (pid == proceso) PostMessage(h, 0x0010, IntPtr.Zero, IntPtr.Zero);
            return true;
        }, IntPtr.Zero);
    }
}
'@

$Logs = Join-Path $env:APPDATA 'obs-studio\logs'

function Aviso($texto) {
    [void][System.Windows.Forms.MessageBox]::Show($texto, 'StopO', 'OK', 'Warning')
}

function Grabando($log) {
    $marcas = Select-String -Path $log -Pattern '==== Recording (Start|Stop) ' | Select-Object -Last 1
    $marcas -and $marcas.Matches[0].Groups[1].Value -eq 'Start'
}

$obs = Get-Process obs64 -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $obs) {
    Aviso 'OBS no está abierto: no hay nada que parar.'
    exit 1
}
$log = (Get-ChildItem $Logs -Filter *.txt | Sort-Object LastWriteTime | Select-Object -Last 1).FullName

if (Grabando $log) {
    # OBS lee los atajos aunque no tenga el foco.
    [Cierre]::CtrlMayusD()
    $limite = (Get-Date).AddSeconds(30)
    while ((Grabando $log) -and (Get-Date) -lt $limite) { Start-Sleep -Milliseconds 500 }
    if (Grabando $log) {
        Aviso 'OBS no ha parado la grabación (¿sigue el atajo Ctrl+Mayús+D en "Detener grabación"?). Párala desde OBS.'
        exit 1
    }
}

[Cierre]::Cerrar($obs.Id)
if (-not $obs.WaitForExit(20000)) {
    Aviso 'La grabación está parada, pero OBS no se ha cerrado. Ciérralo desde el icono de la bandeja.'
    exit 1
}
