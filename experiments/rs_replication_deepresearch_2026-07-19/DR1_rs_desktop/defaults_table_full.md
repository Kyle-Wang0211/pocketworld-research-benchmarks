# RealityScan 桌面版 全设置默认值表(官方 Keys and Values,一手抓取)

- 来源(一手,直连无代理):https://rshelp.capturingreality.com/en-US/tutorials/setkeyvaluetable.htm(抓取 2026-07-18,SHA256=1396379730f95153cec11ef5488b1cda909687bd1b5886a69ee78c2377de6455,存 evidence/tutorials_setkeyvaluetable.htm)
- 交叉源(官方新 docs,经 r.jina.ai 代理,因本网络对 dev.epicgames.com TLS 掐断):https://dev.epicgames.com/documentation/realityscan/keys-and-values(存 evidence/devepic_keys_and_values_via_jina.md)
- 两源核对:对齐(Alignment)段核心参数 100% 一致;仅 2 个控制点先验字段漂移,见文末⚠️。
- 该表即 CLI `set`/`preset` 的键值全表 = UI 默认面板的机器可读形态(Default 列 = UI 默认值)。

## App Settings

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Include subdirectories *relevant for: addFolder command | `appIncSubdirs` | bool | **false** |
| Log file | `appLog` | bool | **true** |
| Operation log data | `operationLog` | bool | **true** |
| Auto save mode | `appAutoSaveMode` | bool | **true** |
| Handling of autosaved projects* *defines how to load autosaved projects (if present) when using load command. More information about Autosave feature here . | `appAutoSaveCliHandling` | delete / recover / abort / ask | **delete** |
| Max points to display | `appMaxPointsToDisplay` | integer | **10000000** |
| Cache location | `appCacheLocation` | SystemTemp / Custom | **SystemTemp** |
| Cache custom location* *relevant for: "appCacheLocation=Custom" | `appCacheCustomLocation` | path | **** |
| Clear cache on exit | `appAutoClearCache` | 999999 – Do not clear cache / 0 – Clear all cache items / 3 – Items older than 3 days / 7 – Items older than 1 week / 14 – Items older than 2 weeks / 30 – Items older than 1 month / 90 – Items older than 3 months | **7 – Items older than 1 week** |
| Cache image metadata | `appCacheImageMetadata` | bool | **true** |
| Allow Read Only* *when set to true, it is possible to open the same project in 2 instances. | `allowReadOnly` | bool | **false** |

### Visual and language settings

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Zoom | `appThemeZoom` | 0 - Use Windows Settings / 1 - 100% / 1.25 - 125% / 1.5 - 150% / 2 - 4K (200%) / 3 - 300% | **0 - Use Windows Settings** |
| Animated UI | `appUIAnim` | bool | **true** |
| UI Language | `UserInterfaceLanguageId` | 2052 - Chinese (simplified) / 1028 - Chinese (traditional) / 1029 - Czech / 1033 - English / 1036 - French / 1031 - German / 1040 - Italian / 1041 - Japanese / 1042 - Korean / 3082 - Spanish | **** |

### Import settings

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Group calibration by exif | `appGroupCalibrationByExif` | bool | **false** |
| Copy imported components to cache | `appCopyImportedComponentsToCache` | bool | **false** |
| Ignore exif GPS | `appIgnoreExifGPS` | bool | **false** |

### Progress and notification

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Minimal process duration | `appProcessActionTime` | int | **15** |
| Action | `appProcessAction` | None / PlaySound / ExecuteProgram | **None** |
| Command-line process* *relevant for: "appProcessAction=ExecuteProgram" | `appProcessExecCmd` | string | **** |

## Alignment Settings

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Feature detection quality | `sfmFeatureDetectionQuality` | High / Normal | **High** |
| Max features per mpx | `sfmMaxFeaturesPerMpx` | int | **10000** |
| Max features per image | `sfmMaxFeaturesPerImage` | int | **40000** |
| Images' overlap | `sfmImagesOverlap` | Low / Medium / High | **Medium** |
| Image downscale factor | `sfmImageDownscaleFactor` | int | **1** |
| Max feature reprojection error | `sfmMaxFeatureReprojectionError` | float | **2.0** |

### Camera priors settings

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Use camera priors for georeferencing | `sfmEnableCameraPrior` | bool | **true** |
| Position X accuracy | `sfmCameraPriorAccuracyX` | float | **10.0** |
| Position Y accuracy | `sfmCameraPriorAccuracyY` | float | **10.0** |
| Position Z accuracy | `sfmCameraPriorAccuracyZ` | float | **20.0** |
| Position prior hardness | `sfmCameraPriorWeight` | float | **1.0** |
| Yaw accuracy | `sfmCameraPriorAccuracyYaw` | float | **10.0** |
| Pitch accuracy | `sfmCameraPriorAccuracyPitch` | float | **10.0** |
| Roll accuracy | `sfmCameraPriorAccuracyRoll` | float | **10.0** |
| Orientation prior hardness | `sfmCameraPriorWeightOrientation` | float | **1.0** |

### Control point prior settings

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Image measurement accuracy [px] | `sfmControPointImageMeasAccuracy` | float | **2.0** |
| Position X accuracy | `sfmControlPointXAccuracy` | float | **0.05** |
| Position Y accuracy | `sfmControlPointYAccuracy` | float | **0.05** |
| Position Z accuracy | `sfmControlPointZAccuracy` | float | **0.10** |
| Defined distance accuracy | `sfmDefinedDistanceAccuracy` | float | **0.10** |

### Draft mode

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Overlap of images | `sfmImagesOverlapDraftMode` | Low / Medium / High | **Medium** |
| Image downscale factor | `sfmImageDownscaleFactorDraftMode` | integer | **2** |
| Final model optimization | `sfmFinalModelOptimizationDraftMode` | bool | **false** |

### Advanced

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Add a reconstruction region after alignment | `sfmAutoReconRegionAfterAlignment` | bool | **true** |
| Force component rematch | `sfmForceComponentRematch` | bool | **false** |
| Preselector features | `sfmPreselectorFeatures` | int | **10000** |
| Detector sensitivity | `sfmDetectorSensitivity` | Low / Medium / High / Ultra | **Medium** |
| Merge georeferenced components | `sfmMergeGeoreferencedComponents` | bool | **false** |
| Distortion model | `sfmDistortionModel` | Division / Brown3 / Brown4 / Brown3WithTangential2 / Brown4WithTangential2 / KplusBrown3WithTangential2 / KplusBrown4WithTangential2 | **Brown3** |
| Prefer images as feature source during import of Z+F scans | `lisPreferImagesAsFeatureSource` | bool | **true** |

## Reconstruction Settings
### Image depth map calculation - Preview model

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Image downscale | `mvsPreviewDownscaleFactor` | int | **4** |

### Image depth map calculation - Normal model

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Image downscale | `mvsNormalDownscaleFactor` | int | **2** |

### LiDAR scans

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Minimal distance between two points | `mvsMinSampleDistanceLaserScan` | float | **0.002** |
| Point-cloud cropping radius | `mvsMaxSampleDistanceLaserScan` | float | **150.0** |
| Minimal intensity | `mvsMinIntensityLaserScan` | float | **0.03** |

### Mesh calculation

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| GPU acceleration | `MvsGeometryGpuAccel` | bool | **true** |
| Remove marginal triangles | `MvsGeometryMarginStyle` | bool | **false** |
| Minimal distance between two vertices | `mvsMinSampleDistance` | float | **0.0** |

### Mesh calculation - Preview model

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Mesh calculaton strategy | `mvsPreviewMeshStrategy` | sfm - Use sparse point cloud / vertexCount - Max vertex count | **sfm** |
| Max vertex count* *relevant for: "mvsPreviewMeshStrategy=vertexCount" | `mvsPreviewMaxVetrexCountInModel` | int | **10000000** |

### Advanced

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Maximal vertex count per part | `mvsMaxVertexCountInPart` | int | **5000000** |
| Detail decimation factor | `mvsDecimationFactor` | float | **1.0** |
| Depth map algorithm version | `MvsDepthMapsLibVersion` | 0 - Version 1 / 1 - Version 2 | **1** |
| Adaptive blending start | `mvsAdaptiveBlendingStart` | float | **0.45** |
| Smoothing | `mvsSmoothingWeight` | float | **1.5** |

### Advanced - Photogrammetry

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Default grouping factor | `mvsDefaultGroupingFactor` | float | **1.0** |
| Low texture grouping factor | `mvsLowTextureGroupingFactor` | float | **0.25** |
| Default noise factor | `mvsDefaultNoiseFactor` | float | **1.0** |
| Low texture noise factor | `mvsLowTextureNoiseFactor` | float | **2.0** |

### Advanced - Mesh filtration

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Filter radius | `mvsFilteringRadius` | float | **3.0** |
| Filter strength | `mvsFilteringStrength` | int | **2** |

### Advanced - Model import

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Maximal vertices' count per part | `mvsImportMaxTrianglesPerPart` | int | **100000000** |

## Color and Texture Settings
### Default unwrap parameters

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Gutter | `unwrapGutter` | int | **2** |
| Minimal texture resolution | `unwrapMinTexResolution` | 512 / 1024 / 2048 / 4096 / 8192 / 16384 | **512** |
| Maximal texture resolution | `unwrapMaxTexResolution` | 512 / 1024 / 2048 / 4096 / 8192 / 16384 | **8192** |
| Large triangle removal threshold | `unwrapLargeTriangleRemovalThr` | int | **10** |
| Style | `unwrapStyle` | MaxTexturesCount / FixedTexelSize / AdaptiveTexelSize | **MaxTexturesCount** |
| Maximal textures' count* *relevant for: "unwrapStyle=MaxTexturesCount" | `unwrapMaximalTexCount` | int | **1** |
| Texel size* *relevant for: "unwrapStyle=FixedTexelSize" | `unwrapFixedTexelSizeType` | 0 - Optimal / 1 - 2x optimal (50% texture quality) / 2 - 4x optimal (25% texture quality) / 3 - 10x optimal (10% texture quality) / 4 - 100x optimal (1% texture quality) / 5 - Custom | **0** |
| Custom texel size* *relevant for: "unwrapStyle=FixedTexelSize" "unwrapFixedTexelSizeType =5" | `unwrapFixedTexelSize` | float | **0.01** |
| Minimal required texel size* *relevant for: "unwrapStyle=AdaptiveTexelSize" | `unwrapMinTexelSize` | 0 - Optimal / 1 – 2x optimal (50% texture quality) / 2 – 4x optimal (25% texture quality) / 3 – 10x optimal (10% texture quality) / 4 – 100x optimal (1% texture quality) / 5 - Custom | **0** |
| Custom minimal required texel size* *relevant for: "unwrapStyle=FixedTexelSize" "unwrapFixedTexelSizeType =5" | `unwrapMinTexelSize` | float | **0.01** |
| Maximal required texel size* *relevant for: "unwrapStyle=AdaptiveTexelSize" | `unwrapMaxTexelSize` | 0 - Optimal / 1 – 2x optimal (50% texture quality) / 2 – 4x optimal (25% texture quality) / 3 – 10x optimal (10% texture quality) / 4 – 100x optimal (1% texture quality) / 5 - Custom | **4** |
| Custom maximal required texel size* *relevant for: "unwrapStyle=FixedTexelSize" "unwrapFixedTexelSizeType =5" | `unwrapMaxTexelSize` | float | **10** |

### Coloring/Texturing

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Imported model default texture resolution | `txtImportDefaultTexResolution` | 512 / 1024 / 2048 / 4096 / 8192 / 16384 | **8192** |
| Coloring method | `txtMethod` | Linear / MultiBand | **MultiBand** |
| Coloring style | `colStyle` | PhotoConsistencyBased / VisibilityBased | **VisibilityBased** |
| Coloring image layer | `ImageLayerForColoring` | geometry/name_of_geometry_layer / texture01/name_of_texture_layer / texture2/name_of_texture_layer2 | **geometry (if no texturing layer is present) texture01 (if any texturing layer is present)** |
| Texturing style | `txtStyle` | PhotoConsistencyBased / VisibilityBased / MosaicingBased / MaximalIntensity / MinimalIntensity / AverageIntensity | **VisibilityBased** |
| Texturing image layer | `ImageLayerForTexturing` | geometry/name_of_geometry_layer / texture01/name_of_texture_layer / texture2/name_of_texture_layer2 / all | **all (All texturing layers)** |
| Downscale images before texturing | `txtImageDownscaleTexture` | int | **1** |
| Downscale images before coloring | `txtImageDownscaleColor` | int | **2** |
| Fill in uncolored parts | `txtFillInUncoloredParts` | bool | **true** |
| Fill in untextured parts | `txtFillInUntextoredParts` | bool | **true** |
| Recolor model after texturing | `txtRecolorAfterTexturing` | bool | **true** |
| Correct colors | `MvsDoCorrectColors` | bool | **false** |
| Ignore color correction | `MvsIgnoreCorrectColors` | bool | **false** |
| Prefer 16-bit/HDR texture generation | `MvsGeometryTexturingDoHdr` | bool | **true** |

## Error-handling Settings

| 设置名(UI) | Key(CLI) | 取值 | **默认值** |
|---|---|---|---|
| Quit on error | `appQuitOnError` | bool | **false** |
| Quit on required restart | `appQuitOnReset` | bool | **false** |
| Suppress error messages | `suppressErrors` | bool | **false** |

## Learn how to use the Set Command

## ⚠️两官方源漂移(仅 2 处,均为控制点先验,与本项目复刻无关)

| Key | rshelp(本表) | dev.epicgames docs |
|---|---|---|
| `sfmControPointImageMeasAccuracy` | 2.0 | 4.0 |
| `sfmDefinedDistanceAccuracy` | 0.10 | 0.001 |

解释:两页均为官方现行文档;dev.epicgames 为 Epic 迁移后的新 canonical,rshelp 为在线帮助。差异字段仅影响 GCP/控制点工作流(我们不用)。核心对齐参数两源一致。
