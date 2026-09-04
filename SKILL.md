---
name: gazebo-windows-conda-fix
description: Fix and run Ignition Gazebo 6 (ign-gazebo / gz sim) on native Windows under a conda (RoboStack ros-humble) environment. This skill should be used when `ign gazebo` fails on Windows with errors such as "Failed to find world", "couldn't find shared library", "Failed to load system plugin", "Failed to copy installed config", QML "module IgnGazebo is not installed", "Failed to find plugin [libignition-physics-dartsim-plugin.so]", ogre shadow crashes (initShadowVolumeMaterials / abort), or DLL error 126 in a ros_gz / ros-humble conda env. Trigger words: ign gazebo, gz sim, Gazebo Windows, conda ros_gz, RoboStack, dartsim, ogre2.
agent_created: true
---

# ROS 2 + Gazebo on Native Windows (conda/RoboStack) — Setup & Fix Guide

## Background

RoboStack conda packages are the practical way to run ROS 2 Humble + Ignition Gazebo 6 on **native Windows** (no WSL/VM). However, the Gazebo 6 packages are broken out of the box: nothing sets the ignition environment variables, conda drops symlinks and mangles DLL names, and the build hard-codes Linux conventions. The result is a stack of ~11 independent failures, each surfacing only after the previous one is fixed. The errors peel like an onion: fix one, run again, hit the next. This skill provides the complete setup workflow plus an idempotent patch script that clears the whole stack.

## Prerequisites

- conda (miniconda/mambaforge) on 64-bit Windows; create the environment with:
  `conda create -n ros_gz -c robostack-humble -c conda-forge ros-humble-ros-base ros-humble-ros-gz`
- The `ign` launcher is a Ruby script: `<env>\Library\bin\ign` (called by `<env>\Library\bin\ign.bat`), which loads `<env>\Library\lib\ruby\ignition\cmdgazebo6.rb`
- Visual Studio BuildTools `dumpbin.exe` for dependency forensics (optional but invaluable)

## Quick Path (recommended)

Run the idempotent patch script from this skill, then launch:

```bash
python scripts/apply_fixes.py --env <env-root>
# then, in an activated conda prompt:
ign gazebo shapes-noshadow.sdf --render-engine-gui ogre
```

`apply_fixes.py` performs every fix listed below (idempotent: safe to re-run). If the ruby wrapper patch step cannot auto-apply (unexpected file layout), follow `references/debug-layers.md` layer 5 to patch `cmdgazebo6.rb` by hand.

## What the script fixes (the full failure stack)

1. **Config seeding** — Gazebo tries to copy `server.config`/`gui.config` from the build-time prefix (does not exist) into `%USERPROFILE%\.ignition\gazebo\6\`. Fix: copy them from `<env>\Library\share\ignition\ignition-gazebo6\` manually.
2. **Ruby wrapper env block** — no activation script sets ignition vars. Patch `cmdgazebo6.rb` to set (unconditionally, gated only on `IGN_GAZEBO_RESOURCE_PATH` being empty): `IGN_GAZEBO_RESOURCE_PATH`, `IGN_FILE_PATH` (worlds dir), `IGN_GUI_PLUGIN_PATH` + `IGN_GAZEBO_GUI_PLUGIN_PATH` (`Library\lib\ign-gui-6\plugins` and `Library\lib\ign-gazebo-6\plugins\gui`), `IGN_GAZEBO_SYSTEM_PLUGIN_PATH` (Library\bin), `IGN_GAZEBO_PHYSICS_ENGINE_PATH` (`Library\lib\ign-physics-5\engine-plugins`), `QML2_IMPORT_PATH` (`...\plugins\gui` + `Library\qml`).
3. **Unversioned DLL aliases** (conda drops the symlink copies):
   - `ignition-gazebo6-*-system.dll` → `ignition-gazebo-*-system.dll` (server.config references unversioned names)
   - `ignition-physics-dartsim-plugin.dll` → `libignition-physics-dartsim-plugin.so` (Physics.cc has the Linux default name baked in; Windows LoadLibrary does not care about the extension, a renamed copy works)
   - `ignition-rendering6-ogre.dll` → `ignition-rendering-ogre.dll` (RenderEngineManager unversioned name)
4. **`libdeflate` alias** — `tiff.dll` needs `libdeflate.dll` but the conda package installs it as `deflate.dll`. Copy one to the other. This single missing DLL kills the whole rendering chain (FreeImage → ignition-common4-graphics → ignition-rendering6 → every rendering GUI plugin, reported as error 126 "module not found").
5. **ogre2 does not exist** — this package ships ogre 1 only. Always launch with `--render-engine-gui ogre`.
6. **ogre1 shadow crash** — with RTSS (RTShaderSystem) present, shadow volume material init (`Ogre::SceneManager::ShadowRenderer::initShadowVolumeMaterials`) throws and aborts on this stack. SDF `<shadows>false</shadows>` and `cast_shadows=false` are NOT enough (the flag is not propagated to the ogre renderer). Fix: rename `<env>\Library\share\ignition\ignition-rendering6\ogre\media\rtshaderlib150` → `rtshaderlib150.disabled`. RTSS then reports "Cannot find OGRE rtshaderlib. Shadows will be disabled." and rendering falls back to the stable fixed-function path. Trade-off: flat materials, no shadows.

## Verification protocol

- **Headless first** (fast, no window): `ign gazebo -s -r --iterations 5 --verbose 4 <world>` — confirms server + physics + systems. Look for `Loaded [ignition::physics::dartsim::Plugin] from library [...]`.
- **Full GUI**: expect ground plane + box/cylinder/sphere/capsule/ellipsoid resting on the ground at z=0.5 (that is the world's design, not a physics failure). To see dynamics, use a world with an object raised (e.g. sphere pose z=8) and watch it drop and bounce.
- **When testing from a script, replicate the user's full conda-activated environment** (PATH order + `IGN_RENDERING_PLUGIN_PATH`, `OGRE_RESOURCE_PATH`, etc.). A test shell missing activation vars can silently take a different (accidentally-working or accidentally-failing) code path and mislead the diagnosis.

## Diagnostic toolbox (when the quick path misses something)

- **Is a DLL loadable with the user's PATH?** Ruby+fiddle repro via `LoadLibraryA` (kernel32), or Python `ctypes.windll.kernel32.LoadLibraryA`. Error 126 = dependency missing (walk the chain), error 127 = proc not found.
- **What does a DLL depend on?** `dumpbin.exe -DEPENDENTS <dll>`; test each dependency individually, then descend into the first failing one (the failure is usually 2–4 levels deep in a transitive dep, not in the plugin itself).
- **What env var does a loader read?** Fetch the component's source (jsDelivr: `https://cdn.jsdelivr.net/gh/gazebosim/<repo>@<branch>/src/<File>.cc`) or scan the DLL's string table for `IGN_*` / env-style names (python `re` over the raw bytes).
- **conda packaging lies**: `conda-meta` can list a package as installed while its DLL has a different filename than consumers expect (the `deflate`/`libdeflate` case). Always verify the actual file in `Library\bin`.

Full layer-by-layer case file (symptoms → root cause → fix, including dead ends): see `references/debug-layers.md`.
