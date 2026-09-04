# ROS 2 Humble + Gazebo on Native Windows (RoboStack/conda) — Complete Setup Guide

A WorkBuddy Skill with the **end-to-end method for configuring ROS 2 Humble and Ignition Gazebo 6 on native Windows** (no WSL, no VM) via the RoboStack conda distribution — including the post-install patches that make `ign gazebo` actually work.

## Why this exists

RoboStack ships ROS 2 + Gazebo as conda packages for Windows, which is the only practical native-Windows route. But the Gazebo packages are broken out of the box: ~11 independent issues (env vars nobody sets, DLLs conda renamed or dropped, a Linux default filename baked into a Windows build, an ogre1 shadow crash). Each failure only surfaces after the previous one is fixed, which makes manual debugging a multi-hour onion-peeling exercise. This skill peels the whole onion in one script.

## Setup

### 1. Create the conda environment (RoboStack win-64)

```bash
conda create -n ros_gz -c robostack-humble -c conda-forge ros-humble-ros-base ros-humble-ros-gz
conda activate ros_gz
```

> Requires conda (miniconda/mambaforge) on 64-bit Windows. If the install transaction dies mid-way, delete the poisoned packages from the `pkgs/` cache and re-run — half-unpacked environments produce misleading "file not found" errors later.

### 2. Apply the post-install patches (one command)

```bash
python scripts/apply_fixes.py --env "E:\Anaconda\envs\ros_gz"
```

Idempotent — safe to re-run. It patches the Ruby launcher, seeds config files, and creates the DLL aliases that conda forgot. See `SKILL.md` for the itemized list.

### 3. Launch Gazebo

```bash
ign gazebo shapes-noshadow.sdf --render-engine-gui ogre
```

> Always pass `--render-engine-gui ogre`: these packages ship ogre 1 only, no ogre2. A `shapes-noshadow.sdf` (shadows disabled — see below) or any world file in the current directory works.

### 4. Verify

- **Headless first**: `ign gazebo -s -r --iterations 5 --verbose 4 <world>` — look for `Loaded [ignition::physics::dartsim::Plugin]`.
- **GUI**: ground plane + box/cylinder/sphere appear in the 3D view. To see dynamics, raise an object (e.g. sphere pose z=8) and watch it drop and bounce.

## What apply_fixes.py does (TL;DR)

| # | Problem in the conda build | Fix |
|---|---|---|
| 1 | `server.config` / `gui.config` never seeded to `%USERPROFILE%\.ignition\gazebo\6\` | copy from `Library/share/ignition/ignition-gazebo6/` |
| 2 | No ignition env vars set anywhere | inject env block into `cmdgazebo6.rb` (resource path, GUI plugin paths, system plugin path, physics engine path, QML import path) |
| 3 | Unversioned DLL aliases dropped by conda | `ignition-gazebo6-*-system.dll` and `ignition-rendering6-ogre.dll` alias copies |
| 4 | Physics engine default filename baked as Linux `.so` | `ignition-physics-dartsim-plugin.dll` → `libignition-physics-dartsim-plugin.so` |
| 5 | `tiff.dll` needs `libdeflate.dll`, package ships `deflate.dll` | alias copy (one missing DLL killed the entire rendering chain) |
| 6 | ogre1 shadow-volume crash via RTSS (`initShadowVolumeMaterials` abort) | `rtshaderlib150` → `rtshaderlib150.disabled`, forced fixed-function rendering |

The full layer-by-layer case file — symptoms, root causes, diagnostic toolbox (`dumpbin` dependency-chain drills, DLL string-table archaeology, headless A/B tests) — lives in [`references/debug-layers.md`](references/debug-layers.md).

## Scope & caveats

- Targets RoboStack `robostack-humble` win-64 builds of Ignition Gazebo 6 (gz-gazebo6 / Fortress-era naming). Other versions: same *method*, different file names — the skill documents how to find each knob.
- ogre1 fixed-function rendering means flat materials and no shadows; fine for simulation, not for beauty shots.
- WSL2 + ros_gz is an alternative on modern Windows; native conda is lighter on RAM and plays better with GPU access in some setups.
