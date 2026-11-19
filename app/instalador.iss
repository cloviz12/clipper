; Instalador de CLIPPER (Inno Setup). Se instala por usuario, sin pedir administrador.
#ifndef Version
  #define Version "1.0.0"
#endif

[Setup]
AppId={{6B1F4F2E-9C3A-4E1B-8F6D-3C1F9E7A2B40}
AppName=CLIPPER
AppVersion={#Version}
AppPublisher=CLIPPER
DefaultDirName={localappdata}\Programs\CLIPPER
DefaultGroupName=CLIPPER
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=salida
OutputBaseFilename=CLIPPER-Setup-{#Version}
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\CLIPPER.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "dist\CLIPPER\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CLIPPER"; Filename: "{app}\CLIPPER.exe"
Name: "{autodesktop}\CLIPPER"; Filename: "{app}\CLIPPER.exe"; Tasks: escritorio

[Run]
Filename: "{app}\CLIPPER.exe"; Description: "Abrir CLIPPER"; Flags: nowait postinstall skipifsilent
; actualizacion automatica (instalacion silenciosa): vuelve a abrir la app en la bandeja
Filename: "{app}\CLIPPER.exe"; Parameters: "--bandeja"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM CLIPPER.exe"; Flags: runhidden; RunOnceId: "cerrar"
