# Crea le icone di ArchieBet (stile tabellone LED) e i collegamenti "Avvia" e "Spegni"
# sul Desktop e nel menu Start. Si puo' rilanciare quando si vuole: sovrascrive tutto.
# Uso (da PowerShell, nella cartella del progetto):
#   powershell -ExecutionPolicy Bypass -File tools\crea-icone.ps1

Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $PSScriptRoot
$iconDir = Join-Path $PSScriptRoot 'icone'
New-Item -ItemType Directory -Force $iconDir | Out-Null

# Lettere a matrice di punti 5x7, come il font LED dell'app: '#' = punto acceso
$patterns = @{
    'A'    = @('.###.', '#...#', '#...#', '#####', '#...#', '#...#', '#...#')
    'stop' = @('.....', '#####', '#####', '#####', '#####', '#####', '.....')
}

function New-LedPng([int]$size, [string[]]$pattern, [System.Drawing.Color]$color) {
    $bmp = New-Object System.Drawing.Bitmap $size, $size
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'AntiAlias'
    $g.Clear([System.Drawing.Color]::Transparent)

    # Fondo scuro con angoli arrotondati (come i pannelli dell'app)
    $r = [Math]::Max(2, [int]($size * 0.18))
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $path.AddArc(0, 0, $r, $r, 180, 90)
    $path.AddArc($size - $r - 1, 0, $r, $r, 270, 90)
    $path.AddArc($size - $r - 1, $size - $r - 1, $r, $r, 0, 90)
    $path.AddArc(0, $size - $r - 1, $r, $r, 90, 90)
    $path.CloseFigure()
    $g.FillPath((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 10, 12, 11))), $path)

    # Griglia 5x7 centrata: punti accesi nel colore scelto con alone, spenti quasi invisibili
    $cell = $size * 0.78 / 7
    $x0 = ($size - 5 * $cell) / 2
    $y0 = ($size - 7 * $cell) / 2
    $dot = $cell * 0.8
    $glow = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(70, $color.R, $color.G, $color.B))
    $lit = New-Object System.Drawing.SolidBrush $color
    $off = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 26, 31, 28))
    for ($row = 0; $row -lt 7; $row++) {
        for ($col = 0; $col -lt 5; $col++) {
            $cx = $x0 + $col * $cell + $cell / 2
            $cy = $y0 + $row * $cell + $cell / 2
            if ($pattern[$row][$col] -eq '#') {
                if ($size -ge 32) { $g.FillEllipse($glow, $cx - $dot * 0.75, $cy - $dot * 0.75, $dot * 1.5, $dot * 1.5) }
                $g.FillEllipse($lit, $cx - $dot / 2, $cy - $dot / 2, $dot, $dot)
            } elseif ($size -ge 32) {
                $g.FillEllipse($off, $cx - $dot / 2, $cy - $dot / 2, $dot, $dot)
            }
        }
    }
    $g.Dispose()
    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    return , $ms.ToArray()
}

# File .ico con dentro le immagini PNG in piu' dimensioni (formato supportato da Windows Vista in poi)
function Save-Ico([string]$file, [string[]]$pattern, [System.Drawing.Color]$color) {
    $sizes = @(256, 48, 32, 16)
    $images = @($sizes | ForEach-Object { , (New-LedPng $_ $pattern $color) })
    $out = New-Object System.IO.MemoryStream
    $w = New-Object System.IO.BinaryWriter $out
    $w.Write([UInt16]0); $w.Write([UInt16]1); $w.Write([UInt16]$sizes.Count)
    $offset = 6 + 16 * $sizes.Count
    for ($i = 0; $i -lt $sizes.Count; $i++) {
        $s = $sizes[$i]
        $w.Write([byte]($s % 256)); $w.Write([byte]($s % 256))  # 256 si scrive come 0
        $w.Write([byte]0); $w.Write([byte]0)
        $w.Write([UInt16]1); $w.Write([UInt16]32)
        $w.Write([UInt32]$images[$i].Length); $w.Write([UInt32]$offset)
        $offset += $images[$i].Length
    }
    foreach ($img in $images) { $w.Write($img) }
    [System.IO.File]::WriteAllBytes($file, $out.ToArray())
}

$amber = [System.Drawing.Color]::FromArgb(255, 255, 176, 0)   # --amber dell'app
$red = [System.Drawing.Color]::FromArgb(255, 255, 107, 94)    # --loss dell'app
$startIco = Join-Path $iconDir 'avvia.ico'
$stopIco = Join-Path $iconDir 'spegni.ico'
Save-Ico $startIco $patterns['A'] $amber
Save-Ico $stopIco $patterns['stop'] $red

# Collegamenti sul Desktop e nel menu Start
$shell = New-Object -ComObject WScript.Shell
$places = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
$links = @(
    @{ Name = 'Avvia ArchieBet'; Bat = 'avvia-archiebet.bat'; Icon = $startIco; Text = 'Avvia ArchieBet e apre il browser' },
    @{ Name = 'Spegni ArchieBet'; Bat = 'spegni-archiebet.bat'; Icon = $stopIco; Text = 'Spegne ArchieBet' }
)
foreach ($place in $places) {
    foreach ($l in $links) {
        $lnk = $shell.CreateShortcut((Join-Path $place "$($l.Name).lnk"))
        $lnk.TargetPath = Join-Path $root $l.Bat
        $lnk.WorkingDirectory = $root
        $lnk.IconLocation = "$($l.Icon),0"
        $lnk.Description = $l.Text
        $lnk.Save()
    }
}

# Chiede a Windows di ridisegnare le icone (altrimenti a volte mostra ancora quelle vecchie)
& "$env:SystemRoot\System32\ie4uinit.exe" -show
Write-Output "Icone create in $iconDir; collegamenti aggiornati su Desktop e menu Start."
