Image Desk 3.2 — Legacy Windows edition

Target: Windows 7 SP1, Windows 8/8.1, Windows 10 and Windows 11.
Choose x86 for 32-bit Windows; choose x64 for 64-bit Windows. The modern
Windows download uses Qt 6 and cannot run on Windows 7/8/8.1.

Extract the ENTIRE ZIP into a short local folder, for example C:\ImageDesk.
Open ImageDesk-Legacy.exe. Keep all DLLs and the PySide2 and vlc folders
beside the executable. Python and VLC do not need to be installed separately.

Windows 7 must have Service Pack 1 and its normal platform/runtime updates,
including KB2533623 (DLL loading) and KB2999226 (Universal C Runtime), or
updates that supersede them. An unpatched Windows 7 installation is not a
supported target. Windows RT and ARM-native Windows are not legacy targets.

The same interface and features are included: still images, MP4/MOV, animated
GIFs, play once/loop, multiple named playlists, sessions, top-left/center
alignment, fullscreen on a second display, blackout and remaining time.
Sessions are interchangeable with Image Desk 3.1 and newer.

The legacy edition uses software video decoding so it does not depend on a
new GPU driver. Playback of large/high-bitrate videos depends on the PC's
CPU and memory; the x86 edition has a smaller address space. Test your actual
show media, display configuration and audio output before a presentation.

Verification status:
The build runs the packaged application's automated decoder and UI checks
on a Windows Server 2022 runner and audits its CPU architecture, PE subsystem
requirements and known incompatible imports. This is NOT certification that
it has run on Windows 7/8/8.1: a target-OS test is still needed.

To test this package on your Windows computer, double-click
Check-compatibility.cmd. It runs the bundled synthetic media checks and opens
a JSON report with success/failure, operating system and runtime details.
It does not change your Windows settings or use your media files. The report
is saved in your temporary folder. Also check fullscreen on the real second
display and audio on the real output device; those cannot be verified by the
automated offscreen check.

If the program cannot start, capture the exact Windows error message.
If it starts but a check fails, send the JSON report with the Windows version.
Legacy dependencies are no longer maintained like the modern runtime; use
the modern build on Windows 10/11 when legacy compatibility is unnecessary.

References:
https://docs.python.org/3.9/using/windows.html
https://doc.qt.io/archives/qt-5.15/windows.html
https://www.videolan.org/vlc/download-windows.html
https://support.microsoft.com/help/2533623
https://support.microsoft.com/help/2999226
