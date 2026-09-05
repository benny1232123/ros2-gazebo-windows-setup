# ROS 2 Humble + Gazebo on Native Windows — Setup Guide

**在 Windows 原生环境（不用 WSL、不用虚拟机）配置 ROS 2 Humble + Ignition Gazebo 6 的完整方法**，基于 RoboStack conda 发行版，并附带让 `ign gazebo` 真正跑起来所需的安装后补丁。

```
ros2-gazebo-windows-setup/
├── README.md                    ← 你在这里：完整配置流程
├── SKILL.md                     ← WorkBuddy Skill 定义（触发条件、修复清单、诊断工具箱）
├── references/debug-layers.md   ← 11 层调试案例档案（症状 → 根因 → 修复）
└── scripts/apply_fixes.py       ← 一键幂等补丁脚本
```

## 原理与背景

RoboStack 把 ROS 2 与 Gazebo 打包成 Windows conda 包，这是原生 Windows 跑 ROS 2 + Gazebo 唯一实际可行的路线。但 Gazebo 相关的包开箱即坏：环境变量没人设、conda 漏装/改名了若干 DLL、构建里还硬编码了 Linux 的文件名约定、ogre1 阴影路径在本机直接崩。这些问题有 11 层，修掉一层才露出下一层，纯手工排查是个几小时的剥洋葱活。

这套指南把整颗洋葱一次性剥完：一个脚本解决，其余文件解释为什么。

## 环境要求

- 64 位 Windows 10/11
- conda（miniconda / mambaforge 均可）
- 可选：Visual Studio BuildTools（`dumpbin.exe` 用于依赖链排查）

## 配置步骤

### 1. 创建 conda 环境

在 PowerShell 或 CMD 里（不要用未激活 conda 的普通 bash）：

```bash
conda create -n ros_gz -c robostack-humble -c conda-forge ^
  ros-humble-desktop ros-humble-ros-ign-gazebo ros-humble-ros-ign-bridge
conda activate ros_gz
```

> 若安装事务中途崩掉（网络/磁盘），把 `pkgs/` 缓存里对应的坏包删掉再重跑——半解包的环境后面会产生极具误导性的"文件找不到"错误。
> `ros-humble-ros-base` 可替换 `ros-humble-desktop`，但后者自带 `demo_nodes_*`，方便后面做 ROS 2 自检。

### 2. 打安装后补丁（一条命令）

```bash
python scripts/apply_fixes.py --env "E:\Anaconda\envs\ros_gz"
```

幂等，可重复执行。它做四件事：给 Ruby 启动器注入环境变量、播种配置文件、补齐 conda 漏掉的 DLL 别名、关掉会崩的 ogre 阴影路径。逐项说明见 `SKILL.md`。

### 3. 启动 Gazebo

**方式 A：直接启动（纯仿真，不挂 ROS 2）**

```bash
ign gazebo shapes-noshadow.sdf --render-engine-gui ogre
```

> `--render-engine-gui ogre` 必须带：这批包只编译了 ogre 1，没有 ogre2。世界文件可以是 `shapes-noshadow.sdf`（关阴影版，见下）或当前目录下任意 `.sdf`。

**方式 B：通过 ROS 2 launch 启动（带 ROS↔Gazebo 桥接）**

```bash
ros2 launch ros_ign_gazebo ign_gazebo.launch.py ign_args:="shapes-noshadow.sdf -r --render-engine-gui ogre"
```

### 4. 验证

**Gazebo 侧**

```bash
# 无头自检（不开窗口，先确认 server + 物理）
ign gazebo -s -r --iterations 5 --verbose 4 shapes-noshadow.sdf
# 出现 Loaded [ignition::physics::dartsim::Plugin] 即物理引擎就位
```

GUI 里应出现地面 + 方块/圆柱/球等几何体。想看物理效果，把某个物体的 z 抬高（例如 z=8），它应该下落并弹跳。

**ROS 2 侧**

```bash
ros2 run demo_nodes_cpp talker          # 另开一个终端：
ros2 run demo_nodes_cpp listener        # 应能收到 hello world
```

**ROS 2 ↔ Gazebo 桥接**

```bash
ros2 run ros_ign_bridge parameter_bridge /clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock
ros2 topic echo /clock                  # 应看到 Gazebo 仿真时间在推进
```

## 补丁脚本做了什么

| # | conda 包里的毛病 | 修复 |
|---|---|---|
| 1 | `server.config` / `gui.config` 从未播种到 `%USERPROFILE%\.ignition\gazebo\6\` | 从 `Library/share/ignition/ignition-gazebo6/` 复制 |
| 2 | 没有任何地方设置 ignition 环境变量 | 向 `cmdgazebo6.rb` 注入环境块（资源路径、GUI 插件路径、系统插件路径、物理引擎路径、QML 导入路径） |
| 3 | conda 丢弃了无版本号的 DLL 别名 | 补 `ignition-gazebo6-*-system.dll`、`ignition-rendering6-ogre.dll` 的别名副本 |
| 4 | 物理引擎默认文件名被硬编码成 Linux 的 `.so` | `ignition-physics-dartsim-plugin.dll` → `libignition-physics-dartsim-plugin.so` |
| 5 | `tiff.dll` 要 `libdeflate.dll`，包里装的却叫 `deflate.dll` | 别名副本（缺这一个 DLL 会拖垮整条渲染链） |
| 6 | ogre1 经 RTSS 的阴影路径崩溃（`initShadowVolumeMaterials` abort） | `rtshaderlib150` → `rtshaderlib150.disabled`，强制固定功能渲染 |

完整的逐层案例（症状、根因、死胡同、诊断方法：`dumpbin` 依赖链下钻、DLL 字符串表考古、无头 A/B 对照）见 [`references/debug-layers.md`](references/debug-layers.md)。

## 作为 WorkBuddy Skill 使用

```bash
# 整目录复制到用户级 skills（复制后重启 WorkBuddy 即生效）
cp -r ros2-gazebo-windows-setup ~/.workbuddy/skills/
```

之后遇到 `ign gazebo` / `ros2 launch` 在 Windows conda 环境下报错时会自动触发这套流程。

## 适用范围与注意事项

- 目标版本：RoboStack `robostack-humble` win-64 的 Ignition Gazebo 6（gz-gazebo6 / Fortress 时代命名）。换版本时方法通用、文件名需自行核对——`references/debug-layers.md` 记录了每一处旋钮是怎么找到的。
- ogre1 固定功能渲染意味着无着色器材质、无阴影：仿真够用，出图不行。
- 现代 Windows 上 WSL2 + ROS 2 是另一条路；原生 conda 更省内存，部分场景下 GPU 访问也更简单。
- Windows 下 ROS 2 命令必须在**已激活的 conda 环境**中运行，否则找不到 `ros2`。
