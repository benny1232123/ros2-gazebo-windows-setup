# Debug Case File: Ignition Gazebo 6 on Windows conda (RoboStack)

Real-world case: env `ros_gz` at `E:\Anaconda\envs\ros_gz`, Windows 10/11 native
(not WSL), RoboStack `ros-humble-ros-gz` packages. Errors peeled in this exact
order; each fix revealed the next failure. All paths below use this env as the
example — substitute your own env root.

Root-cause families behind all 11 layers:

1. **Conda's first install transaction died mid-unpack** — symlinks never
   materialized; the retry skipped packages already flagged in the cache.
2. **No activation script sets ignition env vars** (conda's ign packages rely
   on them; only `libignition-rendering6_activate.bat` sets rendering ones).
3. **The conda build hard-coded Linux conventions** (`.so` default engine name)
   and renamed DLLs inconsistently (`deflate.dll` vs `libdeflate.dll`).

---

## Layer 1 — Empty symlinks / unpack failure
Symptom: myriad "file not found" for files `conda-meta` claims are installed.
Fix: re-run the failed install transaction; delete the poisoned package from
`pkgs/` cache if conda refuses.

## Layer 2 — RMW/DDS error 126
Symptom: `[Err]` lines from rmw/rcl on startup.
Fix: point `RMW_IMPLEMENTATION` / DDS paths at the env (see cmdgazebo6.rb
wrapper or activation scripts).

## Layer 3 — Ruby fiddle export missing
Symptom: Ruby `NoMethodError`/export errors when running `ign`.
Fix: adjust the Ruby launcher (conda Ruby is old); prefer invoking the
launcher exactly as `ign.bat` does (`ruby <env>\Library\bin\ign ...`).

## Layer 4 — Process.fork unavailable
Symptom: `ign gazebo` (server+GUI mode) dies in cmdgazebo6.rb.
Fix: Windows has no fork. Patch the "both" branch to spawn the GUI as a child
process and run the server in-process:

```ruby
guiCmd = [rubyExe, ignScript, 'gazebo', '-g']
guiPid = Process.spawn({'RMT_PORT' => '1501'}, *guiCmd)
ENV['RMT_PORT'] = '1500'
Importer.runServer(...)
```

## Layer 5 — "Failed to find world" / resource path
Symptom: world SDF files not found.
Fix: inside cmdgazebo6.rb, before world resolution:

```ruby
gzLib = File.expand_path('../../..', __dir__)   # -> <env>\Library
worldsDir = File.join(gzLib, 'share', 'ignition', 'ignition-gazebo6', 'worlds')
ENV['IGN_GAZEBO_RESOURCE_PATH'] = worldsDir
ENV['IGN_FILE_PATH'] = worldsDir
```

Also note: gz-sim Server.cc checks `SourceType` ordering — a world passed as a
positional file can be overridden by config defaults; passing the full path or
ensuring the env var is set avoids the trap.

## Layer 6 — "Failed to copy installed config"
Symptom: server/gui want to copy configs from the build prefix
(`D:\bld\libignition-gazebo6_.../server.config`) to `%USERPROFILE%\.ignition\gazebo\6\`.
Fix: seed manually:

```
copy <env>\Library\share\ignition\ignition-gazebo6\server.config   %USERPROFILE%\.ignition\gazebo\6\
copy <env>\Library\share\ignition\ignition-gazebo6\gui\gui.config  %USERPROFILE%\.ignition\gazebo\6\
```

`server.config` matters: it lists the physics/user-commands/scene-broadcaster
system plugins. Without it the server is an empty shell.

## Layer 7 — GUI plugins "couldn't find shared library" (not on path)
Symptom: GUI opens ("Insert plugins to start!") but WorldControl/EntityTree/
CameraManager/... all fail to load.
Fix: they live in two non-standard dirs; set both:

```
IGN_GUI_PLUGIN_PATH=<env>\Library\lib\ign-gui-6\plugins;<env>\Library\lib\ign-gazebo-6\plugins\gui
IGN_GAZEBO_GUI_PLUGIN_PATH=<same>
```

## Layer 8 — Error 126 on every rendering GUI plugin (the libdeflate hunt)
Symptom: plugins are FOUND (full path in the error) but LoadLibrary fails with
126 ("找不到指定的模块" / module not found) = a *dependency* is missing.
Hunt: `dumpbin -DEPENDENTS MinimalScene.dll` → deps all resolve individually
except `ignition-rendering6.dll` → its dep `ignition-common4-graphics.dll` →
dep `FreeImage.dll` → dep `tiff.dll` → dep **`libdeflate.dll` — absent**.
The conda package installs it as `deflate.dll` (conda-meta still claims
libdeflate is installed — packaging lies).
Fix: `copy deflate.dll libdeflate.dll` in `Library\bin`.
Aftermath: re-test the whole chain to green; error 126 for the plugin itself
loaded by bare name is fine (loader uses full path).

## Layer 9 — Server system plugins "couldn't find shared library"
Symptom: `Failed to load system plugin [ignition-gazebo-physics-system]`.
server.config references *unversioned* names; the files on disk are
`ignition-gazebo6-physics-system.dll` etc. (conda dropped the alias copies).
Fix: copy each `ignition-gazebo6-*-system.dll` to the unversioned name, and
point the loader at `Library\bin` via **`IGN_GAZEBO_SYSTEM_PLUGIN_PATH`**
(the name is easy to mis-guess as `..._SERVER_...` — verify against
gz-sim6 `src/SystemLoader.cc`: it reads `IGN_GAZEBO_SYSTEM_PLUGIN_PATH`).

## Layer 10 — Physics: "Failed to find plugin [libignition-physics-dartsim-plugin.so]"
Symptom: `Physics.cc:760` complains, suggests `IGN_GAZEBO_PHYSICS_ENGINE_PATH`.
Root cause: the conda build baked the *Linux* default engine filename into
Physics.cc; no `.so` exists. Windows `LoadLibrary` does not care about the
extension, so a renamed copy works.
Fix: in `Library\lib\ign-physics-5\engine-plugins`:
`copy ignition-physics-dartsim-plugin.dll libignition-physics-dartsim-plugin.so`
and set `IGN_GAZEBO_PHYSICS_ENGINE_PATH` to that directory.
Verify headless: `ign gazebo -s -r --iterations 5 --verbose 4 <world>` →
`Loaded [ignition::physics::dartsim::Plugin] from library [...]`.

## Layer 11 — ogre1 shadow crash (the finale)
Symptom: after `--render-engine-gui ogre`, abort with stack through
`Ogre::Camera::_renderScene` → `SceneManager::ShadowRenderer::initShadowVolumeMaterials`
→ `ManualObject::textureCoord` → `CxxThrowException` → `terminate` → `abort`.
Facts established:
- `--render-engine-gui ogre` is mandatory: **this package has no ogre2**
  (`ign-rendering-6/engine-plugins` only contains the ogre1 plugin).
- SDF `<shadows>false</shadows>` and `<cast_shadows>false</cast_shadows>` do
  NOT prevent the crash — the flag never reaches the ogre renderer.
- The crash is tied to RTSS (RTShaderSystem). When RTShaderLib cannot be
  found, ign-rendering logs "Cannot find OGRE rtshaderlib. Shadows will be
  disabled." and takes a fixed-function path that is stable on this stack.
Fix: make RTShaderLib unfindable:
`rename <env>\Library\share\ignition\ignition-rendering6\ogre\media\rtshaderlib150 → rtshaderlib150.disabled`
Trade-off: flat/no-shader materials, no shadows — acceptable for simulation.
(QML side panels: `module "IgnGazebo" is not installed` is fixed by
`QML2_IMPORT_PATH=<env>\Library\lib\ign-gazebo-6\plugins\gui;<env>\Library\qml`
— the module lives at `...\plugins\gui\IgnGazebo\qmldir`.)

## Post-mortem lessons

- **Replicate the user's full activated environment in scripted tests.** A
  test shell missing `IGN_RENDERING_RESOURCE_PATH` accidentally disabled
  shadows and "proved" the fix worked while the user still crashed. The
  missing variable was both the false positive and, later, the actual fix.
- **Headless server-only runs (`-s`) isolate server-side failures** from the
  GUI/rendering stack; run them before opening any windows.
- **Error 126 ≠ file missing.** It means "found it, but its dependency chain
  is broken" — walk the chain with `dumpbin -DEPENDENTS`, testing each level.
- **conda packaging lies**: verify actual files in `Library\bin` rather than
  trusting `conda-meta` or package plans.
- **Useless-looking env combos can be the fix**: "Shadows will be disabled."
  in the log is a green flag on this stack, not an error to chase.
