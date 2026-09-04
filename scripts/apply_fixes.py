#!/usr/bin/env python3
"""Apply all known fixes for Ignition Gazebo 6 (conda RoboStack build) on Windows.

Idempotent: safe to run repeatedly. Pure stdlib.

Usage:
    python apply_fixes.py --env "E:\\Anaconda\\envs\\ros_gz"

Steps performed:
  1. Seed %USERPROFILE%\\.ignition\\gazebo\\6\\ with server.config / gui.config
  2. Patch Library/lib/ruby/ignition/cmdgazebo6.rb with the Windows env-var block
  3. Create unversioned DLL aliases (gazebo system plugins, dartsim .so, ogre engine)
  4. Create libdeflate.dll alias (conda installs it as deflate.dll)
  5. Disable RTSS (rtshaderlib150 -> rtshaderlib150.disabled) to avoid the
     ogre1 shadow-volume crash on Windows
"""
import argparse
import glob
import os
import shutil
import sys

MARKER = "IGN_GAZEBO_PHYSICS_ENGINE_PATH"  # presence == already patched

ENV_BLOCK_SNIPPET = """\
        ENV['IGN_GAZEBO_SYSTEM_PLUGIN_PATH'] = File.join(gzLib, 'bin')
        ENV['GZ_SIM_SYSTEM_PLUGIN_PATH'] = File.join(gzLib, 'bin')
        ENV['IGN_GAZEBO_PHYSICS_ENGINE_PATH'] = File.join(gzLib, 'lib',
          'ign-physics-5', 'engine-plugins')
        ENV['QML2_IMPORT_PATH'] = File.join(gzLib, 'lib', 'ign-gazebo-6',
          'plugins', 'gui') + ';' + File.join(gzLib, 'qml')
"""


def seed_configs(env: str) -> None:
    share = os.path.join(env, "Library", "share", "ignition", "ignition-gazebo6")
    dest = os.path.join(os.path.expanduser("~"), ".ignition", "gazebo", "6")
    os.makedirs(os.path.join(dest, "gui"), exist_ok=True)
    for src, dst in (
        (os.path.join(share, "server.config"), os.path.join(dest, "server.config")),
        (os.path.join(share, "gui", "gui.config"), os.path.join(dest, "gui.config")),
    ):
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            print(f"[seed] {dst}")
        elif os.path.exists(dst):
            print(f"[seed] exists, skip: {dst}")
        else:
            print(f"[seed] WARN source missing: {src}")


def patch_ruby_wrapper(env: str) -> None:
    rb = os.path.join(env, "Library", "lib", "ruby", "ignition", "cmdgazebo6.rb")
    if not os.path.exists(rb):
        print("[ruby] WARN cmdgazebo6.rb not found, skip")
        return
    with open(rb, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    if MARKER in text:
        print("[ruby] already patched, skip")
        return
    anchor = "ENV['IGN_FILE_PATH'] = worldsDir"
    if anchor not in text:
        print("[ruby] WARN anchor not found; patch manually (see SKILL.md layer 5)")
        return
    # Keep a one-time backup
    bak = rb + ".orig"
    if not os.path.exists(bak):
        shutil.copy2(rb, bak)
        print(f"[ruby] backup -> {bak}")
    text = text.replace(anchor, anchor + "\n" + ENV_BLOCK_SNIPPET.rstrip("\n"), 1)
    with open(rb, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("[ruby] env block injected")


def alias(env: str, src_name: str, dst_name: str, base: str) -> None:
    src = os.path.join(base, src_name)
    dst = os.path.join(base, dst_name)
    if os.path.exists(dst):
        print(f"[alias] exists, skip: {dst_name}")
        return
    if not os.path.exists(src):
        print(f"[alias] WARN source missing: {src}")
        return
    shutil.copy2(src, dst)
    print(f"[alias] {src_name} -> {dst_name}")


def create_aliases(env: str) -> None:
    bin_ = os.path.join(env, "Library", "bin")
    # 1. unversioned gazebo system plugin aliases
    for f in glob.glob(os.path.join(bin_, "ignition-gazebo6-*-system.dll")):
        name = os.path.basename(f)
        alias_name = name.replace("ignition-gazebo6-", "ignition-gazebo-", 1)
        alias(env, name, alias_name, bin_)
    # 2. dartsim physics engine with the Linux-style default name
    ep = os.path.join(env, "Library", "lib", "ign-physics-5", "engine-plugins")
    alias(env, "ignition-physics-dartsim-plugin.dll",
          "libignition-physics-dartsim-plugin.so", ep)
    # 3. unversioned ogre render engine plugin
    rep = os.path.join(env, "Library", "lib", "ign-rendering-6", "engine-plugins")
    alias(env, "ignition-rendering6-ogre.dll", "ignition-rendering-ogre.dll", rep)
    # 4. libdeflate (conda package ships deflate.dll, tiff.dll wants libdeflate.dll)
    alias(env, "deflate.dll", "libdeflate.dll", bin_)


def disable_rtss(env: str) -> None:
    media = os.path.join(env, "Library", "share", "ignition",
                         "ignition-rendering6", "ogre", "media")
    rtss = os.path.join(media, "rtshaderlib150")
    off = rtss + ".disabled"
    if os.path.exists(off):
        print("[rtss] already disabled, skip")
        return
    if os.path.exists(rtss):
        os.rename(rtss, off)
        print("[rtss] rtshaderlib150 -> rtshaderlib150.disabled "
              "(avoids ogre1 shadow-volume crash)")
    else:
        print("[rtss] WARN rtshaderlib150 not found under " + media)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env", required=True, help="conda env root, e.g. E:\\Anaconda\\envs\\ros_gz")
    args = ap.parse_args()
    env = os.path.abspath(args.env)
    if not os.path.isdir(env):
        print(f"ERROR: env root not found: {env}")
        return 2
    print(f"=== Patching Gazebo conda env: {env} ===")
    seed_configs(env)
    patch_ruby_wrapper(env)
    create_aliases(env)
    disable_rtss(env)
    print("=== Done. Launch with:  ign gazebo <world> --render-engine-gui ogre ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
