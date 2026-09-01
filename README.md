# RockSynth

RockSynth 使用 BlenderProc 生成可控、可复现的岩石场景，可输出多机位 RGB、深度、实例分割等数据。

## 环境配置

```bash
conda env create -f environment.yml
conda activate rock-synth
blenderproc quickstart
```

## 准备资产

生成器只使用已下载并预处理的扫描岩石资产。首次运行前，请按照[资产说明](docs/assets.md)准备岩石和地表材质。

## 生成场景

使用默认配置：

```bash
blenderproc run scripts/generate_scene.py
```

指定输出目录和随机种子：

```bash
blenderproc run scripts/generate_scene.py \
  --output output/example \
  --seed 11
```

使用其他配置：

```bash
blenderproc run scripts/generate_scene.py \
  --config configs/scene.json \
  --output output/custom
```

场景参数位于 `configs/scene.json`，包括地形、岩石数量与范围、相机、光照和物理求解参数。

## 输出内容

```text
output/example/
├── 0.hdf5
├── 1.hdf5
├── ...
├── terrain_height.npy
└── scene_metadata.json
```

- `N.hdf5`：RGB、米制 Z 深度和实例标注；
- `terrain_height.npy`：地形高度场；
- `scene_metadata.json`：资产来源、岩石属性、相机参数和逐帧可见性。

详细格式见[输出数据约定](docs/output-schema.md)。

## 检查和查看结果

检查单帧：

```bash
python scripts/inspect_output.py output/example --frame 0
```

检查全部相机帧：

```bash
python scripts/inspect_output.py output/example --all
```

显示检查窗口：

```bash
python scripts/inspect_output.py output/example --frame 0 --show
```

直接查看 HDF5：

```bash
blenderproc vis hdf5 output/example/0.hdf5
```



## Blender 3D 调试

```bash
blenderproc debug scripts/generate_scene.py
```

Blender 打开后：

1. 在 `Scripting` 工作区点击 `Run BlenderProc`；
2. 等待场景构建和物理沉降完成；
3. 切换到 `Layout`；
4. 按 `Home` 显示全部对象；
5. 按小键盘 `0` 切换相机；
6. 按 `Z` 选择 `Material Preview` 或 `Rendered`。

## 测试

```bash
pytest -q
ruff check .
```
