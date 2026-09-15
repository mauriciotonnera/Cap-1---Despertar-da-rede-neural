# Image Desk

Image Desk shows an image and its file information in a control window on the computer's main display. A second, borderless fullscreen window shows just the image on the selected display. It works on Windows, macOS, and Linux with Python 3.10 or newer and PySide6.

## Install and run

1. Install Python 3.10+ from [python.org](https://www.python.org/downloads/). On Windows, check **Add Python to PATH** if offered.
2. Open a terminal in this folder and install the dependency:

   ```sh
   python -m pip install -r requirements.txt
   ```

   On macOS/Linux, use `python3` in place of `python` if needed.

3. Start the program:

   ```sh
   python viewer.py
   ```

   You can also pass a path, for example `python viewer.py "photo.jpg"`. After installing the dependency, Windows users can double-click `launch_windows.bat` and macOS users can double-click `launch_mac.command` (allow the script to run if macOS asks).

## Controls

- **Open image…** or drag an image onto the window. The right panel shows the name, folder, format, dimensions, file size, modification time, and transparency.
- Choose a display. When two displays are connected, the secondary display is chosen automatically. A single-display computer can also show fullscreen on its only display.
- Choose **Fit** to see the entire image, **Fill** to crop it to the screen, or **Actual size** to show one image pixel per logical screen pixel.
- Click **Show fullscreen** or press **F11**. Press **Esc** in fullscreen to return. Use the left and right arrow keys to move through images in the same folder; the preview and fullscreen window stay synchronized.
- If a selected display disconnects, fullscreen closes. You can change the selected display while fullscreen is running.

The viewer uses Qt's image decoders. Typical installations support JPEG, PNG, BMP, GIF, TIFF, WebP, and ICO; animated files display their first frame. Very large files depend on available memory and Qt's image allocation limit. Camera orientation stored in EXIF is applied automatically.

## Build a standalone Windows or Mac app

The build scripts install their own temporary Python environment. The resulting app does **not** require Python on the computer where you run it.

- On Windows, open PowerShell in this folder and run `powershell -ExecutionPolicy Bypass -File .\build_windows.ps1`. The finished app is `dist\ImageDesk.exe`.
- On macOS, open Terminal in this folder and run `./build_mac.sh`. The finished app is `dist/ImageDesk.app`. This produces a build for the Mac's current processor (Intel or Apple Silicon).

For cloud builds, put the **contents of this folder** at the root of a GitHub repository, open **Actions → Build Image Desk desktop apps → Run workflow**, then download the Windows, Intel Mac, or Apple Silicon Mac build from that run's **Artifacts**. Each artifact download is a ZIP. Unzip the Windows artifact to get the `.exe`. Unzip a Mac artifact to get a `.dmg` containing the `.app`.

These personal builds are not signed with a commercial developer certificate or notarized by Apple. If a downloaded Mac app is blocked, use Finder's **Open** option for it. For wider distribution, sign and notarize the Mac app with your Apple Developer credentials.
