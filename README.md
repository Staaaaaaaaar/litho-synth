# LithoSynth

LithoSynth 是面向岩石多样性研究的场景合成、数据生成与分析工具。

项目当前以 BlenderProc 为后端，优先建立一个简单、可控且可重复的多岩石场景闭环。后续将根据研究需要逐步扩展地形、岩石、材质和其他合成数据后端。

## 当前范围

- 多岩石场景构建与渲染
- RGB、深度、实例标注和已知属性导出
- 基于已知属性的场景与数据集多样性分析
- 基础检查与可视化

## 项目状态

项目处于 v0.1.0 开发阶段，已提供最小多岩石场景生成流程。当前方案见 [docs/plan/v0.1.0.md](docs/plan/v0.1.0.md)。

## 开发环境

```bash
conda env create -f environment.yml
conda activate lithosynth
blenderproc quickstart
```

项目使用 Conda、Python 3.11 和 BlenderProc 2.8.0。BlenderProc 首次运行时会在 Conda 环境之外安装并管理其所需的 Blender，项目脚本统一通过 `blenderproc run` 执行。是否直接使用 `bpy`，待具体场景需求明确后再决定。

## 生成最小场景

使用默认配置生成场景：

```bash
blenderproc run scripts/generate_scene.py
```

覆盖输出目录或随机种子：

```bash
blenderproc run scripts/generate_scene.py --output output/example --seed 11
```

默认配置位于 `configs/scene.json`。输出目录包含：

- `0.hdf5`：RGB、深度和实例标注；
- `scene_metadata.json`：随机种子、相机参数以及生成时已知的地形和岩石属性。

可使用 BlenderProc 自带工具查看 HDF5：

```bash
blenderproc vis hdf5 output/demo/0.hdf5
```

在 Blender GUI 中构建和检查场景：

```bash
blenderproc debug scripts/generate_scene.py
```

Blender 打开后，在 Scripting 工作区点击 `Run BlenderProc`。入口脚本同时兼容普通运行和 GUI 调试模式。

## 检查与可视化

检查 HDF5 数据集、图像尺寸、相机分辨率以及实例与岩石元数据的一致性，并生成综合检查图：

```bash
python scripts/inspect_output.py output/demo
```

检查图默认写入 `output/demo/inspection.png`，包含 RGB、深度、实例标注以及岩石位置、尺寸、基础颜色和粗糙度。若当前环境支持图形界面，可同时打开窗口：

```bash
python scripts/inspect_output.py output/demo --show
```

## 代码边界

```text
generators → core/spec.py: SceneSpec → backends → render outputs
```

- `core/` 保存配置加载与跨层共享的场景契约；
- `generators/` 负责地形、岩石、空间布置和场景参数生成；
- `core/spec.py` 中的 `SceneSpec` 是与渲染引擎无关的场景描述；
- `backends/` 只负责将场景描述交给 BlenderProc 等具体渲染引擎并导出结果。

后续可参考或迁移已有合成项目中的地形、岩石和分布算法到 `generators/`，不将这些项目本身作为渲染后端。

## v0.1.0 状态

v0.1.0 已建立场景生成、渲染、数据导出、输出检查与可视化的最小闭环。详细验收结果见 [v0.1.0 计划](docs/plan/v0.1.0.md)。
