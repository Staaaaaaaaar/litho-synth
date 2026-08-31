# 场景资产

项目使用程序化高度场地形和纯 CC0 扫描岩石。岩石生成仅接受许可明确、可重新下载并可校验哈希的预处理资产。

## 目录约定

```text
assets/
├── manifests/          # 受 Git 管理的资产来源与格式约定
├── manifest.lock.json  # 下载文件 SHA-256
├── licenses/           # 许可说明与官方链接
├── cache/              # 原始下载，不进入 Git
└── prepared/           # 规范化 .blend 与指标，不进入 Git
```

manifest 必须记录 provider、asset ID、来源页、许可、首选格式、真实尺度、坐标约定和纹理色彩空间。lock 文件锁定实际下载文件，而不是短期下载 URL。

## 获取资产

先离线查看将要解析的下载：

```bash
python scripts/assets/download_assets.py --asset polyhaven:rock_09 --dry-run
```

确认后执行下载并更新 lock：

```bash
for asset in rock_09 boulder_01 namaqualand_boulder_03 namaqualand_boulder_04; do
  python scripts/assets/download_assets.py --asset "polyhaven:${asset}"
done
```

工具拒绝无筛选的批量下载，避免意外获取大型 8K 资产。Poly Haven 与 ambientCG 的原始文件均为 CC0，但项目仍保留来源和许可记录。

## 规范化岩石

下载后通过 Blender 逐个规范化：

```bash
for asset in rock_09 boulder_01 namaqualand_boulder_03 namaqualand_boulder_04; do
  blender --background --python scripts/assets/preprocess_rocks.py -- --asset "polyhaven:${asset}"
done
```

预处理统一米制和 Z-up、应用旋转与缩放、重定位原点，检查网格闭合性，并计算真实尺寸、表面积和体积。输出 `.blend` 是 Blender 后端的内部规范资产；GLB 是交换和归档格式，PLY 保留原始扫描，OBJ 仅作为兼容格式。

无法形成闭合网格或体积无效的资产不会进入对象体积真值基准。渲染网格与碰撞代理分离，物理布置优先使用 convex hull，复杂凹形资产可离线缓存 V-HACD。

默认地表使用 Poly Haven 的 `dense_sand`。下载器会锁定 `.blend` 主文件及其纹理依赖，准备脚本从依赖中识别 PBR 通道并生成元数据：

```bash
python scripts/assets/download_assets.py --asset polyhaven:dense_sand
python scripts/assets/prepare_surface.py --asset polyhaven:dense_sand
```

默认配置会检测 `assets/prepared/polyhaven/dense_sand/metadata.json`；存在时使用 Base Color、Roughness、OpenGL Normal 和 Displacement 贴图，不存在时回退到确定性的程序化沙地材质。

## PBR 纹理

- Base Color：sRGB PNG；
- Roughness、Normal、AO：Non-Color PNG，normal 统一为 OpenGL 方向；
- Height/Displacement：16-bit PNG/TIFF 或 float EXR；
- 岩石按电介质处理，Metallic 固定为 0；
- 纹理必须记录实际覆盖尺寸，避免不同对象出现错误 texel scale。

渲染端使用 Nishita 天空提供环境补光，以有限角度的太阳灯产生柔和阴影，并通过 AgX 色彩管理保留浅色沙地与岩石高光细节。

扫描岩石资产缺失、物理指标无效或材质缺失时生成流程会直接报错，不提供程序化或 hybrid 回退。
