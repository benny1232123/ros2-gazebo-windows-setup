# gazebo-windows-conda-fix

A WorkBuddy Skill that fixes **Ignition Gazebo 6 (RoboStack conda build) on native Windows**.

`ign gazebo` under a `ros-humble-ros-gz` conda env on Windows fails out of the box — not with one bug, but with an ~11-layer stack of them (env vars nobody sets, DLLs conda renamed/dropped, a Linux default filename baked into a Windows build, an ogre1 shadow crash). This skill documents the full failure stack and ships an **idempotent patch script**.

## Usage

```bash
python scripts/apply_fixes.py --env "E:/Anaconda/envs/ros_gz"

# then, in an activated conda prompt:
ign gazebo shapes-noshadow.sdf --render-engine-gui ogre
```

The script is safe to re-run (idempotent). See `SKILL.md` for what it fixes and `references/debug-layers.md` for the full layer-by-layer debug case file.

## What's broken in the conda build (TL;DR)

| # | Problem | Fix in script |
|---|---|---|
| 1 | `server.config` / `gui.config` never seeded | copy from `Library/share/ignition/ignition-gazebo6/` |
| 2 | No ignition env vars set | inject env block into `cmdgazebo6.rb` (resource paths, GUI plugin paths, system plugin path, physics engine path, QML import path) |
| 3 | Unversioned DLL aliases dropped | `ignition-gazebo6-*-system.dll`, `ignition-rendering6-ogre.dll` aliases |
| 4 | Physics engine name baked as Linux `.so` | `ignition-physics-dartsim-plugin.dll` → `libignition-physics-dartsim-plugin.so` |
| 5 | `tiff.dll` needs `libdeflate.dll`, package ships `deflate.dll` | alias copy |
| 6 | ogre1 shadow-volume crash (RTSS path) | `rtshaderlib150` → `rtshaderlib150.disabled` (forced fixed-function rendering) |

> Always launch with `--render-engine-gui ogre` — this package ships no ogre2.
