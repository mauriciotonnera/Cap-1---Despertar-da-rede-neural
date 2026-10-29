# Image Desk 3.3

Image Desk keeps a preview and file information on your main display, with a clean fullscreen view on a selected display. Version 3.0 adds mixed-media playlists, automatic playback, presentation blackout, a remaining-time display and portable saved sessions, keeping the original dark interface.

Version 3.1 adds selectable **Top left (0, 0)** or **Center** alignment and multiple named playlists. Every playlist keeps its own files, order, still-image duration and repeat setting. Sessions save the entire collection and alignment choice.

Version 3.3 adds a separate **Legacy Windows** edition targeting updated Windows 7 SP1 through Windows 11, in both x86 and x64 builds. It uses Python 3.8.10, Qt 5.15.2 / PySide2 and bundled VLC 3 decoding while sharing the same interface, playlists and session format. See [Legacy Windows requirements and verification](WINDOWS-LEGACY.md).

The modern Windows build requires Windows 10/11. The legacy build is a portable folder: extract the entire ZIP and run `ImageDesk-Legacy.exe`, keeping its DLLs and subfolders together. Native builds are automatically exercised on current Windows runners; Windows 7/8/8.1 remain target platforms pending tests on those actual OS versions. A dependency audit is not a substitute for that testing.

## Use the app

Download the Windows executable or the Mac disk image from the latest successful **Build Image Desk 3.3 native apps** run. Extract the downloaded ZIP. On Windows, open `ImageDesk.exe`. On Mac, open the DMG and drag `ImageDesk.app` into Applications. The packaged apps do not require Python. Mac builds require macOS 13 or later; choose Intel or Apple Silicon to match your Mac.

- Click **Open media…** or drop a file onto the window. Images, MP4, MOV and animated GIF files use the same preview and file-information panel.
- Videos and animated GIFs start playing when opened. **Play once** stops and holds the final frame. **Loop** repeats the current file until you pause it or open another file. This choice also overrides the loop count embedded in a GIF and stays selected as you change files during the session.
- Use **Play / Pause**, **Restart**, and the timeline below the preview. The GIF timeline shows frame numbers. Video includes a time display, volume slider and mute control.
- Choose the presentation display and click **Show fullscreen**. The secondary display is selected automatically when available. Opening or closing fullscreen does not restart playback: both windows receive frames from the same player, and audio plays once through the system output. To use HDMI audio, select that output in your computer's sound settings.
- Use the **Alignment** dropdown above the preview to choose **Top left (0, 0)** or **Center**. This applies to images, videos and GIFs in both preview and fullscreen. It can be changed during playback without restarting the media; the default is Top left.
- **Fit**, **Fill** and **Actual size** control the fullscreen presentation. Fit shows the whole frame; Fill crops overflow; Actual size uses one media pixel per logical screen pixel. Top-left alignment keeps the media origin at (0, 0), placing unused space or cropping on the right and bottom. Center alignment distributes it around the media. The main preview always uses Fit with the selected alignment.
- The file panel shows file details and dimensions, plus duration, frame rate and codec when available for video, or frame count for GIFs. Rotated video and EXIF image orientation are respected.
- Previous and Next move through supported media in the current folder. A disconnected presentation display closes fullscreen safely.

Keyboard: **Ctrl+O** (Windows) or **Command+O** (Mac) opens a file; **F11** toggles fullscreen; **Esc** closes fullscreen; **Left / Right** changes files. **Space** plays or pauses video/GIF content and advances to the next file for still images.

## Playlists and automatic playback

Use **+ Add playlist** to create and name another playlist, **Rename…** to change the current playlist's name, and the playlist dropdown to switch between them. Names must be unique and contain 1–80 characters. Adding a playlist selects the new empty list; previous lists keep their media and settings. Use Stop before adding or switching playlists. Renaming is available during playback too.

1. Select the playlist you want to edit, then click **Add files…** to select several images, videos or GIFs. Dropping multiple media files onto the main window also adds them to that playlist. Duplicate files are allowed.
2. Select an item and use the **up/down buttons** to change its position. Select one or more items and click **Remove** to remove them from the list; original files are never deleted.
3. Set **Stills** to the display duration for still images (0.5–3,600 seconds) in this playlist. Single-frame GIFs use this duration too. Videos and animated GIFs play through once before advancing.
4. Click **Start playlist** to begin from the selected item (or the first item). Double-clicking an item starts the playlist there. **Pause playlist / Resume** and **Space** pause or resume the entire sequence, including a still image's countdown. **Stop** pauses the current item and ends automatic advance. Previous/Next follow the active playlist.
5. Enable **Repeat playlist** to repeat this playlist's full sequence. Without repeat, the last item remains visible when finished. The individual clip's Play once/Loop setting is temporarily suspended during a playlist, then restored when it stops. Playback stays within the selected playlist and does not automatically move into another named playlist.

The panel shows the current item number and next file. Stop playback before adding, removing or reordering items. Missing or unreadable items are skipped; an entirely unreadable repeating list stops instead of cycling forever. Clicking **Open media…** opens a standalone file and stops playlist automation. The **Playlist** toolbar button hides or reveals the panel, and its divider can be dragged to resize it.

## Presentation controls

- **Blackout (B)** makes the fullscreen output completely black while preserving the main preview. Playback, playlist advance and audio continue. Use **Mute** separately to silence video audio. Blackout stays enabled across file changes and reopening fullscreen; click **Restore output (B)** to reveal the current frame.
- **Remaining in current item** shows a countdown for video, animated GIFs and timed still images. GIFs briefly show frames remaining while their timing is scanned. A standalone still image shows **Held**. The counter follows pause and seek operations; in a repeating clip it counts the current pass.
- **Show countdown on fullscreen** adds the counter to the bottom-right of the audience display. It is off by default and is always hidden during blackout. With it off, the countdown stays on the operator's screen.

## Save and reopen a show

**Save session…** (Ctrl+S / Command+S) saves an `.imagedesk.json` file containing every named playlist, its media order, still duration and repeat setting, the selected playlist, alignment, fullscreen sizing, countdown visibility, volume and mute. If there is just one empty playlist, the currently open media file is saved as a one-item list.

Use **Open session…**, drop a session file onto the app, or pass it on the command line to reopen it. Loading a session restores all playlists and selects the saved one; it does not start playback or open fullscreen automatically. Missing files remain listed with a **missing** label so they can be identified and replaced. An invalid session leaves the current collection intact.

Existing Image Desk 3.0/3.0.1 sessions open as one playlist named **Playlist 1**. Version 1 and 2 sessions retain their media and settings, with each item's volume defaulting to 100%. New sessions use format version 3 and require Image Desk 3.3 or later. Up to 100 playlists and 10,000 media entries in total can be saved in one session.

## Audio monitoring and transport (3.3)

- The stereo meter beside the main preview shows decoded **sample peaks in dBFS**, with a green/yellow/red scale, peak holds and full-scale indicators. Click it to reset peak holds. It follows item volume, master volume and mute, before the operating system's mixer. Mono appears on both bars; multichannel sources show front L/R in modern builds and the stereo mix in the legacy build. It is not a loudness (LUFS) or true-peak meter. The meter stays on the operator screen.
- Select any playlist row to adjust **Item volume** from 0–100%. Each entry has its own value, even when the same file appears twice. Its percentage appears in the row. Changes to the playing entry take effect immediately; values follow entries when reordered and are saved in sessions. **Master** remains independent: 50% item × 80% master = 40% output. Opening standalone media resets its item volume to 100%.
- **Previous, Pause, Play, Restart and Next** use round icon buttons beneath the preview. They control the active playlist, including timed stills; otherwise they control the current file and its folder. Space still toggles play/pause.
- Drag the playhead to **skim video frames during the drag**. Playback and playlist timing pause while dragging, then restore their previous play/pause state on release. The fullscreen output follows the same frames. Seeking is coalesced to keep long drags responsive.
- The current-item countdown now includes animated GIF time. A second countdown shows the **remaining time in the selected playlist**, including timed stills. Durations are read asynchronously without playing those items. While scanning it shows *Calculating…*; an unreadable duration is marked *+ ?*, and missing/skipped files add no time. Repeat mode counts the remainder of the current pass and labels it accordingly. Both timers follow pause, seek and item changes.

Sessions reference media files; they do not copy or embed them. Keep the session and its media in the same folder structure when moving the show to another computer. Relative paths are used where possible; files on a different Windows drive use an absolute path. Screen selection and blackout state belong to the current operator session and are not restored from a saved show.

## Supported media

Still images include JPEG, PNG, BMP, TIFF, WebP and ICO. GIF files play their animation. Video extensions include MP4, MOV, M4V, AVI, MKV and WebM. Containers can hold different codecs; playback depends on whether the bundled Qt/FFmpeg backend can decode that file's codec. Unsupported or damaged videos show a playback error and can be replaced by opening another file.

The packaged playback checks exercise H.264/AAC MP4, ProRes MOV, rotated MOV and animated GIFs, including looping, last-frame hold, seeking, fullscreen frame sharing and recovery from an invalid file. They also check mixed playlists, still countdowns, repeat and pause, blackout rendering, corrupt/missing items, single-frame GIF timing, both alignments in each sizing mode, naming dialogs, independent playlists, portable collections and migration of older sessions. These checks do not replace testing with physical monitors and audio equipment. Very large images and high-resolution video depend on the computer's available memory and decoding performance.

## Run from source

Use Python 3.12 (the version used for the native builds):

```sh
python -m pip install -r requirements.txt
python viewer.py
```

Use `python3` on macOS/Linux if needed. An optional file argument opens that file immediately, for example `python viewer.py "clip.mov"` or `python viewer.py "My-show.imagedesk.json"`. Keep the Python modules together. `playback.py` owns the shared media player; `playlist.py` manages sequence transitions and still timing; `session.py` reads and writes saved shows.

## Build standalone apps

The modern build scripts install pinned PySide6, QtPy and PyInstaller dependencies in their own `.build-venv`. The legacy build uses its own Python 3.8 environment and pinned PySide2/VLC toolchain.

- Legacy Windows: select Python **3.8.10** (x86 or x64), install 7-Zip, then run `powershell -ExecutionPolicy Bypass -File .\build_windows_legacy.ps1 -Architecture x64` (or `x86`). Output: `dist\ImageDesk-Legacy\ImageDesk-Legacy.exe` and its companion files. Run `python verify_build.py --legacy`. The build verifies the VideoLAN download checksum, stages the pinned runtime DLLs and audits known Windows-version incompatibilities.
- Windows: run `powershell -ExecutionPolicy Bypass -File .\build_windows.ps1`. Output: `dist\ImageDesk.exe`.
- Mac: run `./build_mac.sh`. Output: `dist/ImageDesk.app`, for the current Mac's processor. Run `./package_mac.sh Intel` or `./package_mac.sh Apple-Silicon` to create a DMG with the app and an Applications shortcut.
- Run `python verify_build.py` after building to launch the actual packaged executable and check playback. The report is written to `dist/playback-check.json`. `test_media.json` contains small synthetic test clips bundled for these checks.

The repository's `.github/workflows/image-desk-build.yml` builds Windows x64, Intel Mac and Apple Silicon Mac on pushes to the dedicated `imagedesk-native-build` branch. Every build runs the packaged playback checks before uploading its artifact; Mac builds also verify the DMG and app layout.

These personal builds are not signed with a commercial developer certificate or notarized by Apple. Operating-system security prompts may appear. For wider distribution, sign the Windows executable and sign and notarize the Mac app with the appropriate developer credentials.

For the Mac build downloaded from this repository, if macOS says Apple could not verify the app, click **Done**, then go to **System Settings → Privacy & Security → Security → Open Anyway** and confirm **Open**. Try opening the app from Applications again if the option is not visible. See [Apple's first-launch guidance](https://support.apple.com/en-us/102445).
