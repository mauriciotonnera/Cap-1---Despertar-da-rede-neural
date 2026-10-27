# Image Desk 3.0.1

Image Desk keeps a preview and file information on your main display, with a clean fullscreen view on a selected display. Version 3.0 adds mixed-media playlists, automatic playback, presentation blackout, a remaining-time display and portable saved sessions, keeping the original dark interface.

Version 3.0.1 anchors every image, video and GIF at the media area's top-left corner, coordinate **(0, 0)**, in both the main preview and fullscreen output.

## Use the app

Download the Windows executable or the Mac disk image from the latest successful **Build Image Desk 3.0.1 native apps** run. Extract the downloaded ZIP. On Windows, open `ImageDesk.exe`. On Mac, open the DMG and drag `ImageDesk.app` into Applications. The packaged apps do not require Python. Mac builds require macOS 13 or later; choose Intel or Apple Silicon to match your Mac.

- Click **Open media…** or drop a file onto the window. Images, MP4, MOV and animated GIF files use the same preview and file-information panel.
- Videos and animated GIFs start playing when opened. **Play once** stops and holds the final frame. **Loop** repeats the current file until you pause it or open another file. This choice also overrides the loop count embedded in a GIF and stays selected as you change files during the session.
- Use **Play / Pause**, **Restart**, and the timeline below the preview. The GIF timeline shows frame numbers. Video includes a time display, volume slider and mute control.
- Choose the presentation display and click **Show fullscreen**. The secondary display is selected automatically when available. Opening or closing fullscreen does not restart playback: both windows receive frames from the same player, and audio plays once through the system output. To use HDMI audio, select that output in your computer's sound settings.
- **Fit**, **Fill** and **Actual size** control the fullscreen presentation. All modes start at the top-left corner. Fit shows the whole frame with unused space on the right or bottom; Fill crops any overflow at the right or bottom. Actual size uses one media pixel per logical screen pixel, also starting at (0, 0). The main preview uses Fit with the same top-left alignment.
- The file panel shows file details and dimensions, plus duration, frame rate and codec when available for video, or frame count for GIFs. Rotated video and EXIF image orientation are respected.
- Previous and Next move through supported media in the current folder. A disconnected presentation display closes fullscreen safely.

Keyboard: **Ctrl+O** (Windows) or **Command+O** (Mac) opens a file; **F11** toggles fullscreen; **Esc** closes fullscreen; **Left / Right** changes files. **Space** plays or pauses video/GIF content and advances to the next file for still images.

## Playlists and automatic playback

1. Click **Add files…** in the playlist panel to select several images, videos or GIFs. Dropping multiple media files onto the main window also adds them to the playlist. Duplicate files are allowed.
2. Select an item and use the **up/down buttons** to change its position. Select one or more items and click **Remove** to remove them from the list; original files are never deleted.
3. Set **Stills** to the display duration for still images (0.5–3,600 seconds). Single-frame GIFs use this duration too. Videos and animated GIFs play through once before advancing.
4. Click **Start playlist** to begin from the selected item (or the first item). Double-clicking an item starts the playlist there. **Pause playlist / Resume** and **Space** pause or resume the entire sequence, including a still image's countdown. **Stop** pauses the current item and ends automatic advance. Previous/Next follow the active playlist.
5. Enable **Repeat playlist** to repeat the full sequence. Without repeat, the last item remains visible when finished. The individual clip's Play once/Loop setting is temporarily suspended during a playlist, then restored when it stops.

The panel shows the current item number and next file. Stop playback before adding, removing or reordering items. Missing or unreadable items are skipped; an entirely unreadable repeating list stops instead of cycling forever. Clicking **Open media…** opens a standalone file and stops playlist automation. The **Playlist** toolbar button hides or reveals the panel, and its divider can be dragged to resize it.

## Presentation controls

- **Blackout (B)** makes the fullscreen output completely black while preserving the main preview. Playback, playlist advance and audio continue. Use **Mute** separately to silence video audio. Blackout stays enabled across file changes and reopening fullscreen; click **Restore output (B)** to reveal the current frame.
- **Remaining in current item** shows a countdown for video and timed still images. Animated GIFs show frames remaining. A standalone still image shows **Held**. The counter follows pause and seek operations; in a repeating clip it counts the current pass.
- **Show countdown on fullscreen** adds the counter to the bottom-right of the audience display. It is off by default and is always hidden during blackout. With it off, the countdown stays on the operator's screen.

## Save and reopen a show

**Save session…** (Ctrl+S / Command+S) saves an `.imagedesk.json` file containing playlist order, still duration, repeat settings, fullscreen sizing, countdown visibility, volume and mute. If the playlist is empty, the currently open media file is saved as a one-item list.

Use **Open session…**, drop a session file onto the app, or pass it on the command line to reopen it. Loading a session does not start playback or open fullscreen automatically. Missing files remain listed with a **missing** label so they can be identified and replaced. An invalid session leaves the current playlist intact.

Sessions reference media files; they do not copy or embed them. Keep the session and its media in the same folder structure when moving the show to another computer. Relative paths are used where possible; files on a different Windows drive use an absolute path. Screen selection and blackout state belong to the current operator session and are not restored from a saved show.

## Supported media

Still images include JPEG, PNG, BMP, TIFF, WebP and ICO. GIF files play their animation. Video extensions include MP4, MOV, M4V, AVI, MKV and WebM. Containers can hold different codecs; playback depends on whether the bundled Qt/FFmpeg backend can decode that file's codec. Unsupported or damaged videos show a playback error and can be replaced by opening another file.

The packaged playback checks exercise H.264/AAC MP4, ProRes MOV, rotated MOV and animated GIFs, including looping, last-frame hold, seeking, fullscreen frame sharing and recovery from an invalid file. They also check mixed playlists, still countdowns, repeat and pause, blackout rendering, corrupt/missing items, single-frame GIF timing, and session portability and validation. These checks do not replace testing with physical monitors and audio equipment. Very large images and high-resolution video depend on the computer's available memory and decoding performance.

## Run from source

Use Python 3.12 (the version used for the native builds):

```sh
python -m pip install -r requirements.txt
python viewer.py
```

Use `python3` on macOS/Linux if needed. An optional file argument opens that file immediately, for example `python viewer.py "clip.mov"` or `python viewer.py "My-show.imagedesk.json"`. Keep the Python modules together. `playback.py` owns the shared media player; `playlist.py` manages sequence transitions and still timing; `session.py` reads and writes saved shows.

## Build standalone apps

The build scripts install pinned PySide6 and PyInstaller dependencies in their own `.build-venv`.

- Windows: run `powershell -ExecutionPolicy Bypass -File .\build_windows.ps1`. Output: `dist\ImageDesk.exe`.
- Mac: run `./build_mac.sh`. Output: `dist/ImageDesk.app`, for the current Mac's processor. Run `./package_mac.sh Intel` or `./package_mac.sh Apple-Silicon` to create a DMG with the app and an Applications shortcut.
- Run `python verify_build.py` after building to launch the actual packaged executable and check playback. The report is written to `dist/playback-check.json`. `test_media.json` contains small synthetic test clips bundled for these checks.

The repository's `.github/workflows/image-desk-build.yml` builds Windows x64, Intel Mac and Apple Silicon Mac on pushes to the dedicated `imagedesk-native-build` branch. Every build runs the packaged playback checks before uploading its artifact; Mac builds also verify the DMG and app layout.

These personal builds are not signed with a commercial developer certificate or notarized by Apple. Operating-system security prompts may appear. For wider distribution, sign the Windows executable and sign and notarize the Mac app with the appropriate developer credentials.

For the Mac build downloaded from this repository, if macOS says Apple could not verify the app, click **Done**, then go to **System Settings → Privacy & Security → Security → Open Anyway** and confirm **Open**. Try opening the app from Applications again if the option is not visible. See [Apple's first-launch guidance](https://support.apple.com/en-us/102445).
