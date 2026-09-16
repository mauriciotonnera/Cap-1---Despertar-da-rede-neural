# Image Desk 2.0

Image Desk keeps a preview and file information on your main display, with a clean fullscreen view on a selected display. Version 2.0 keeps the original interface and adds video and animated GIF playback.

## Use the app

Download the Windows executable or the Mac disk image from the latest successful **Build Image Desk 2.0 native apps** run. Extract the downloaded ZIP. On Windows, open `ImageDesk.exe`. On Mac, open the DMG and drag `ImageDesk.app` into Applications. The packaged apps do not require Python. Mac builds require macOS 13 or later; choose Intel or Apple Silicon to match your Mac.

- Click **Open media…** or drop a file onto the window. Images, MP4, MOV and animated GIF files use the same preview and file-information panel.
- Videos and animated GIFs start playing when opened. **Play once** stops and holds the final frame. **Loop** repeats the current file until you pause it or open another file. This choice also overrides the loop count embedded in a GIF and stays selected as you change files during the session.
- Use **Play / Pause**, **Restart**, and the timeline below the preview. The GIF timeline shows frame numbers. Video includes a time display, volume slider and mute control.
- Choose the presentation display and click **Show fullscreen**. The secondary display is selected automatically when available. Opening or closing fullscreen does not restart playback: both windows receive frames from the same player, and audio plays once through the system output. To use HDMI audio, select that output in your computer's sound settings.
- **Fit**, **Fill** and **Actual size** control the fullscreen presentation. Fit shows the whole frame; Fill crops to the display. Actual size uses one media pixel per logical screen pixel.
- The file panel shows file details and dimensions, plus duration, frame rate and codec when available for video, or frame count for GIFs. Rotated video and EXIF image orientation are respected.
- Previous and Next move through supported media in the current folder. A disconnected presentation display closes fullscreen safely.

Keyboard: **Ctrl+O** (Windows) or **Command+O** (Mac) opens a file; **F11** toggles fullscreen; **Esc** closes fullscreen; **Left / Right** changes files. **Space** plays or pauses video/GIF content and advances to the next file for still images.

## Supported media

Still images include JPEG, PNG, BMP, TIFF, WebP and ICO. GIF files play their animation. Video extensions include MP4, MOV, M4V, AVI, MKV and WebM. Containers can hold different codecs; playback depends on whether the bundled Qt/FFmpeg backend can decode that file's codec. Unsupported or damaged videos show a playback error and can be replaced by opening another file.

The packaged playback checks exercise H.264/AAC MP4, ProRes MOV, rotated MOV and animated GIFs, including looping, last-frame hold, seeking, fullscreen frame sharing and recovery from an invalid file. These checks do not replace testing with physical monitors and audio equipment. Very large images and high-resolution video depend on the computer's available memory and decoding performance.

## Run from source

Use Python 3.10 or newer:

```sh
python -m pip install -r requirements.txt
python viewer.py
```

Use `python3` on macOS/Linux if needed. An optional file argument opens that file immediately, for example `python viewer.py "clip.mov"`. Keep `viewer.py` and `playback.py` together. `playback.py` owns the single playback clock shared by the preview and fullscreen windows.

## Build standalone apps

The build scripts install pinned PySide6 and PyInstaller dependencies in their own `.build-venv`.

- Windows: run `powershell -ExecutionPolicy Bypass -File .\build_windows.ps1`. Output: `dist\ImageDesk.exe`.
- Mac: run `./build_mac.sh`. Output: `dist/ImageDesk.app`, for the current Mac's processor. Run `./package_mac.sh Intel` or `./package_mac.sh Apple-Silicon` to create a DMG with the app and an Applications shortcut.
- Run `python verify_build.py` after building to launch the actual packaged executable and check playback. The report is written to `dist/playback-check.json`. `test_media.json` contains small synthetic test clips bundled for these checks.

The repository's `.github/workflows/image-desk-build.yml` builds Windows x64, Intel Mac and Apple Silicon Mac on pushes to the dedicated `imagedesk-native-build` branch. Every build runs the packaged playback checks before uploading its artifact; Mac builds also verify the DMG and app layout.

These personal builds are not signed with a commercial developer certificate or notarized by Apple. Operating-system security prompts may appear. For wider distribution, sign the Windows executable and sign and notarize the Mac app with the appropriate developer credentials.
