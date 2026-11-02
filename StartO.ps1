# StartO - abre OBS grabando la ventana de la reunion de Teams en curso.
# Genera la coleccion de escenas "Teams reunion" a partir de la habitual
# ("Sin Título", que no se toca): la "Captura de ventana" apunta a la ventana de
# la reunion, escalada al lienzo, y la "Captura de pantalla" queda oculta.
# Graba en C:\V, que es donde la recoge LauncherV. Se para con StopO.ps1.
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class Ventanas {
    delegate bool EnumProc(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr p);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
    public static List<object[]> Listar() {
        var r = new List<object[]>();
        EnumWindows((h, p) => {
            if (!IsWindowVisible(h)) return true;
            var t = new StringBuilder(512); GetWindowText(h, t, 512);
            if (t.Length == 0) return true;
            var c = new StringBuilder(256); GetClassName(h, c, 256);
            uint pid; GetWindowThreadProcessId(h, out pid);
            r.Add(new object[] { h, t.ToString(), c.ToString(), (int)pid });
            return true;
        }, IntPtr.Zero);
        return r;
    }
}
'@

$Base = 'Sin Título'
$Coleccion = 'Teams reunion'
$ObsDir = 'C:\Program Files\obs-studio\bin\64bit'
$ObsCfg = Join-Path $env:APPDATA 'obs-studio'

function Aviso($texto) {
    [void][System.Windows.Forms.MessageBox]::Show($texto, 'StartO', 'OK', 'Warning')
}

# Asigna una propiedad aunque no exista en el JSON.
function Fija($obj, $nombre, $valor) {
    $obj | Add-Member -NotePropertyName $nombre -NotePropertyValue $valor -Force
}

if (Get-Process obs64 -ErrorAction SilentlyContinue) {
    Aviso 'OBS ya está abierto. Ciérralo (o pulsa Iniciar grabación en él) y vuelve a usar el icono.'
    exit 1
}

# Ventanas de Teams (cliente nuevo y clásico).
$pids = @{}
Get-Process ms-teams, Teams -ErrorAction SilentlyContinue | ForEach-Object { $pids[$_.Id] = "$($_.ProcessName).exe" }
$teams = [Ventanas]::Listar() | Where-Object { $pids.ContainsKey($_[3]) } | ForEach-Object {
    [pscustomobject]@{ Handle = $_[0]; Titulo = $_[1]; Clase = $_[2]; Exe = $pids[$_[3]] }
}
if (-not $teams) {
    Aviso 'No hay ninguna ventana de Teams abierta. Entra en la reunión y vuelve a usar el icono.'
    exit 1
}

# La ventana principal lleva la sección delante (Chat | ..., Calendario | ...);
# la de la reunión lleva su título. Si queda una sola, es esa; si no, se elige.
$secciones = '^(Chat|Actividad|Activity|Calendario|Calendar|Teams|Llamadas|Calls|Personas|People|Copilot|OneDrive|Aplicaciones|Apps|Comunidades|Communities|Microsoft Teams)\b'
$reuniones = @($teams | Where-Object { $_.Titulo -notmatch $secciones })
if ($reuniones.Count -eq 1) {
    $ventana = $reuniones[0]
} else {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'StartO - elige la ventana de la reunión'
    $form.Size = New-Object System.Drawing.Size(560, 300)
    $form.StartPosition = 'CenterScreen'
    $form.TopMost = $true
    $lista = New-Object System.Windows.Forms.ListBox
    $lista.Dock = 'Fill'
    $teams | ForEach-Object { [void]$lista.Items.Add($_.Titulo) }
    $lista.SelectedIndex = 0
    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = 'Grabar'
    $ok.Dock = 'Bottom'
    $ok.DialogResult = 'OK'
    $form.AcceptButton = $ok
    $form.Controls.Add($lista)
    $form.Controls.Add($ok)
    $lista.Add_DoubleClick({ $form.DialogResult = 'OK' })
    if ($form.ShowDialog() -ne 'OK') { exit 1 }
    $ventana = @($teams)[$lista.SelectedIndex]
}

# Minimizada no se captura.
if ([Ventanas]::IsIconic($ventana.Handle)) { [void][Ventanas]::ShowWindow($ventana.Handle, 9) }

# Formato de OBS: titulo:clase:exe, con '#' y ':' escapados.
function Codifica($s) { $s.Replace('#', '#22').Replace(':', '#3A') }
$destino = '{0}:{1}:{2}' -f (Codifica $ventana.Titulo), (Codifica $ventana.Clase), (Codifica $ventana.Exe)

# Tamaño del lienzo, del perfil activo.
$ini = Get-Content (Join-Path $ObsCfg 'global.ini') -Encoding UTF8
$perfil = ($ini | Select-String '^ProfileDir=(.*)$').Matches[0].Groups[1].Value
$basic = Get-Content (Join-Path $ObsCfg "basic\profiles\$perfil\basic.ini") -Encoding UTF8
$ancho = [double](($basic | Select-String '^BaseCX=(\d+)').Matches[0].Groups[1].Value)
$alto = [double](($basic | Select-String '^BaseCY=(\d+)').Matches[0].Groups[1].Value)

$escenas = Join-Path $ObsCfg 'basic\scenes'
$json = Get-Content (Join-Path $escenas "$Base.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$json.name = $Coleccion
# Audio: el de la coleccion base apunta a dispositivos concretos (auriculares
# que cambian de perfil o ya no existen) y OBS graba en silencio. Aqui, los
# predeterminados de Windows, sin segundo audio de escritorio y sin silenciar
# (en OBS el medidor se mueve aunque la fuente este silenciada).
foreach ($dev in 'DesktopAudioDevice1', 'AuxAudioDevice1') {
    if ($json.$dev) {
        Fija $json.$dev.settings 'device_id' 'default'
        Fija $json.$dev 'muted' $false
    }
}
$json.PSObject.Properties.Remove('DesktopAudioDevice2')
foreach ($src in $json.sources) {
    if ($src.id -eq 'window_capture') {
        Fija $src.settings 'window' $destino
        Fija $src.settings 'method' 2     # Windows Graphics Capture: Teams sale en negro con BitBlt
        Fija $src.settings 'priority' 1   # si cambia algo, buscar por titulo y no por exe
    }
}
foreach ($src in $json.sources | Where-Object { $_.id -eq 'scene' }) {
    foreach ($item in $src.settings.items) {
        $tipo = ($json.sources | Where-Object { $_.name -eq $item.name }).id
        if ($tipo -eq 'monitor_capture') { $item.visible = $false }
        if ($tipo -eq 'window_capture') {
            $item.visible = $true
            # Escalar dentro del lienzo, arriba a la izquierda (coordenadas absolutas y relativas de OBS 31+).
            Fija $item 'pos' ([pscustomobject]@{ x = 0.0; y = 0.0 })
            Fija $item 'pos_rel' ([pscustomobject]@{ x = - $ancho / $alto; y = -1.0 })
            Fija $item 'align' 5
            Fija $item 'bounds_type' 2
            Fija $item 'bounds_align' 0
            Fija $item 'bounds' ([pscustomobject]@{ x = $ancho; y = $alto })
            Fija $item 'bounds_rel' ([pscustomobject]@{ x = 2 * $ancho / $alto; y = 2.0 })
        }
    }
}
if (-not ($json.sources | Where-Object { $_.id -eq 'window_capture' })) {
    Aviso "La colección '$Base' de OBS no tiene ninguna Captura de ventana."
    exit 1
}
[IO.File]::WriteAllText((Join-Path $escenas "$Coleccion.json"), ($json | ConvertTo-Json -Depth 100), (New-Object Text.UTF8Encoding($false)))

Start-Process (Join-Path $ObsDir 'obs64.exe') -WorkingDirectory $ObsDir -ArgumentList @(
    '--collection', "`"$Coleccion`"", '--startrecording', '--minimize-to-tray', '--disable-shutdown-check')
