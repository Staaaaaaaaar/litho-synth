# 输出数据约定

每个场景输出到独立目录：

```text
scene/
├── 0.hdf5
├── 1.hdf5
├── ...
├── terrain_height.npy
└── scene_metadata.json
```

## 坐标与深度

- 世界单位为米，Z 轴向上；
- `T_world_camera` 是 OpenGL 相机坐标到世界坐标的 4×4 变换；
- 相机内参以 `K` 保存，像素坐标原点位于图像左上角；
- `depth` 是 BlenderProc 输出的相机前向 Z 深度，单位为米，不是光心到表面的欧氏距离；
- 图像数组形状为 `(height, width)`，配置中的分辨率顺序为 `(width, height)`。

## 每帧 HDF5

最低数据集：

- `colors`：RGB，`uint8`；
- `depth`：Z 深度，`float32`；
- `instance_segmaps`：实例索引；
- `rock_id_segmaps`：稳定的场景级岩石 ID；
- `instance_attribute_maps`：当前帧实例索引到名称、类别和岩石 ID 的映射。

同一岩石的 `rock_id` 在一个场景的所有帧中保持不变。单帧只需要包含场景岩石的子集。

## 场景元数据

`scene_metadata.json` 包含：

- 随机种子和渲染后端信息；
- 地形物理范围、高度场摘要、材质和 `terrain_height.npy` 的引用；
- 每块岩石的资产来源、最终位置、旋转、尺寸、表面积、体积、颜色、粗糙度和埋入比例；
- 相机 rig、共享内参、裁剪范围、背景占比上限与所有局部俯拍机位；
- 每帧的 `T_world_camera`、实际背景占比、可见岩石 ID、像素数、图像占比和二维包围框。

默认物理模式下埋入比例恒为 0。启用 `render.physics` 时，配置校验会拒绝非零 `bury_fraction_range`，避免在刚体沉降后人为下移岩石。

岩石位姿用于复现和生成标注，输出不将 6D 位姿作为目标训练任务。

## 输出验收

检查器要求：

- 每帧背景占比不超过对应相机的 `max_background_fraction`；
- 全部机位的可见岩石并集覆盖场景中的所有岩石；
- 高度场文件形状和哈希与元数据一致；
- 岩石尺寸、表面积和体积均有效；
- HDF5 图像、深度和实例标注形状一致。
