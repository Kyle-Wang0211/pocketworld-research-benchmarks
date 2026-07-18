Title: Keys and Values | Realityscan Documentation | Epic Developer Community

URL Source: https://dev.epicgames.com/documentation/realityscan/keys-and-values

Markdown Content:
The command-line interface (CLI) in RealityScan allows users to modify various application settings using the **set** or **preset** command. Each command requires a **key** (which identifies the setting to change) and a corresponding **value**. The tables below list the available keys and their value types for the basic settings.

## Application Settings

Adjust the application settings, located in the Application section of the Workflow tab.

| Name | Key | Value | Default value |
| --- | --- | --- | --- |
| Include subdirectories (_relevant for addFolder command_) | appIncSubdirs | true false | false |
| Log file | appLog | true false | true |
| Operation log data | operationLog | true false | true |
| Auto save mode | appAutoSaveMode | true false | true |
| Handling of autosaved projects (_defines how to load autosaved projects if present when using the load command_) | appAutoSaveCliHandling | delete recover abort ask | delete |
| Max points to display | appMaxPointsToDisplay | number (integer) | 10000000 |
| Cache location | appCacheLocation | SystemTemp Custom | SystemTemp |
| Cache custom location (_relevant for "appCacheLocation=Custom"_) | appCacheCustomLocation | path |  |
| Clear cache on exit | appAutoClearCache | 999999 (_Do not clear cache_) 0 (_Clear all cache i_ _\_tem\_ s_) 3 (Items older than 3 days) 7 (_Items older than 1 week_) _14 (Items older than 2 weeks)_ 30 (_Items older than 1 month_) 90 (_Items older than 3 months_) | 7 (_Items older than 1 week_) |
| Cache image metadata | appCacheImageMetadata | true false | true |
| Allow Read Only (_when set to true, it is possible to open the same project in 2 instances_) | allowReadOnly | true false | false |
| Visual and language settings |  |  |  |
| Zoom | appThemeZoom | 0 _(Use Windows Settings)_ 1 _(100%)_ 1.25 _(125%)_ 1.5 _(150%)_ 2 _(4K, 200%)_ 3 _(300%)_ | 0 _(Use Windows Settings)_ |
| Animated UI | appUIAnim | true false | true |
| UI Language | UserInterfaceLanguageId | 2052 _(Chinese – Simplified)_ 1028 _(Chinese – Traditional)_ 1029 _(Czech)_ 1033 _(English)_ 1036 _(French)_ 1031 _(German)_ 1040 _(Italian)_ 1041 _(Japanese)_ 1042 _(Korean)_ 308 _(Spanish)_ |  |
| Import settings |  |  |  |
| Group calibration by exif | appGroupCalibrationByExif | true false | false |
| Copy imported components to cache | appCopyImportedComponentsToCache | true false | false |
| Ignore exif GPS | appIgnoreExifGPS | true false | false |
| Progress and notification |  |  |  |
| Minimal process duration | appProcessActionTime | number (integer) |  |
| Action | appProcessAction | None PlaySound ExecuteProgram | None |
| Command-line process (_relevant for "appProcessAction=ExecuteProgram"_) | appProcessExecCmd | text (string) |  |

## Alignment Settings

Change the alignment settings, located in the Registration section of the ALIGNMENT tab.

| Name | Key | Value | Default |
| --- | --- | --- | --- |
| Feature detection quality | sfmFeatureDetectionQuality | High Normal | High |
| Max features per mpx | sfmMaxFeaturesPerMpx | number (integer) | 10000 |
| Max features per image | sfmMaxFeaturesPerImage | number (integer) | 40000 |
| Image overlap | sfmImagesOverlap | Low Medium High | Medium |
| Image downscale factor | sfmImageDownscaleFactor | number (integer) | 1 |
| Max feature reprojection error | sfmMaxFeatureReprojectionError | number (float) | 2.0 |
| Camera priors settings |  |  |  |
| Use camera priors for georeferencing | sfmEnableCameraPrior | true false | true |
| Position X accuracy | sfmCameraPriorAccuracyX | number (float) | 10.0 |
| Position Y accuracy | sfmCameraPriorAccuracyY | number (float) | 10.0 |
| Position Z accuracy | sfmCameraPriorAccuracyZ | number (float) | 20.0 |
| Position prior hardness | sfmCameraPriorWeight | number (float) | 1.0 |
| Yaw accuracy | sfmCameraPriorAccuracyYaw | number (float) | 10.0 |
| Pitch accuracy | sfmCameraPriorAccuracyPitch | number (float) | 10.0 |
| Roll accuracy | sfmCameraPriorAccuracyRoll | number (float) | 10.0 |
| Orientation prior hardness | sfmCameraPriorWeightOrientation | number (float) | 1.0 |
| Control point prior settings |  |  |  |
| Image measurement accuracy [px] | sfmControPointImageMeasAccuracy | number (float) | 4.0 |
| Position X accuracy | sfmControlPointXAccuracy | number (float) | 0.05 |
| Position Y accuracy | sfmControlPointYAccuracy | number (float) | 0.05 |
| Position Z accuracy | sfmControlPointZAccuracy | number (float) | 0.1 |
| Defined distance accuracy | sfmDefinedDistanceAccuracy | number (float) | 0.001 |
| Draft mode |  |  |  |
| Overlap of images | sfmImagesOverlapDraftMode | Low Medium High | Medium |
| Image downscale factor | sfmImageDownscaleFactorDraftMode | number (integer) | 2 |
| Final model optimization | sfmFinalModelOptimizationDraftMode | true false | false |
| Advanced |  |  |  |
| Add a reconstruction region after alignment | sfmAutoReconRegionAfterAlignment | true false | true |
| Force component rematch | sfmForceComponentRematch | true false | false |
| Preselector features | sfmPreselectorFeatures | number (integer) | 10000 |
| Detector sensitivity | sfmDetectorSensitivity | Low Medium High Ultra | Medium |
| Merge georeferenced components | sfmMergeGeoreferencedComponents | true false | false |
| Distortion model | sfmDistortionModel | Division Brown3 Brown4 Brown3WithTangential2 Brown4WithTangential2 KplusBrown3WithTangential2 KplusBrown4WithTangential2 | Brown3 |
| Prefer images as feature source during import of Z+F scans | lisPreferImagesAsFeatureSource | true false | true |

## Reconstruction Settings

Adjust the reconstruction settings, which affect the model creation. These settings are located in the Create Mesh section of the MESH & COLOR tab.

| Name | Key | Value | Default |
| --- | --- | --- | --- |
| Image depth map calculation - Preview model |  |  |  |
| Image downscale | mvsPreviewDownscaleFactor | number (integer) | 4 |
| Image depth map calculation - Normal model |  |  |  |
| Image downscale | mvsNormalDownscaleFactor | number (integer) | 2 |
| LiDAR scans |  |  |  |
| Minimal distance between two points | mvsMinSampleDistanceLaserScan | number (float) | 0.002 |
| Point-cloud cropping radius | mvsMaxSampleDistanceLaserScan | number (float) | 150.0 |
| Minimal intensity | mvsMinIntensityLaserScan | number (float) | 0.0 |
| Mesh calculation |  |  |  |
| GPU acceleration | MvsGeometryGpuAccel | true false | true |
| Remove marginal triangles | MvsGeometryMarginStyle | true false | true |
| Minimal distance between two vertices | mvsMinSampleDistance | number (float) | 0.0 |
| Mesh calculation - Preview model |  |  |  |
| Mesh calculaton strategy | mvsPreviewMeshStrategy | sfm (_Use sparse point cloud_) vertexCount (_Max vertex count_) | sfm |
| Max vertex count (_relevant for "mvsPreviewMeshStrategy=vertexCount"_) | mvsPreviewMaxVetrexCountInModel | number (integer) | 10000000 |
| Advanced |  |  |  |
| Maximal vertex count per part | mvsMaxVertexCountInPart | number (integer) | 5000000 |
| Detail decimation factor | mvsDecimationFactor | number (float) | 1.0 |
| Depth map algorithm version | MvsDepthMapsLibVersion | 0 (_Version 1_) 1 (_Version 2_) | 1 |
| Adaptive blending start | mvsAdaptiveBlendingStart | number (float) | 0.45 |
| Smoothing | mvsSmoothingWeight | number (float) | 1.5 |
| Advanced - Photogrammetry |  |  |  |
| Default grouping factor | mvsDefaultGroupingFactor | number (float) | 1.0 |
| Low texture grouping factor | mvsLowTextureGroupingFactor | number (float) | 0.25 |
| Default noise factor | mvsDefaultNoiseFactor | number (float) | 1.0 |
| Low texture noise factor | mvsLowTextureNoiseFactor | number (float) | 2.0 |
| Advanced - Mesh filtration |  |  |  |
| Filter radius | mvsFilteringRadius | number (float) | 3.0 |
| Filter strength | mvsFilteringStrength | number (integer) | 2 |
| Advanced - Model import |  |  |  |
| Maximal vertex count per part | mvsImportMaxTrianglesPerPart | number (integer) | 100000000 |

## Color and Texture Settings

Change the settings for coloring and texturing. These settings are located in the Color & Texture section of the Mesh & Color tab.

| Name | Key | Value | Default |
| --- | --- | --- | --- |
| Default unwrap parameters |  |  |  |
| Gutter | unwrapGutter | number (integer) | 2 |
| Minimal texture resolution | unwrapMinTexResolution | 512 1024 2048 4096 8192 16384 | 512 |
| Maximal texture resolution | unwrapMaxTexResolution | 512 1024 2048 4096 8192 16384 | 8192 |
| Large triangle removal threshold | unwrapLargeTriangleRemovalThr | number (integer) | 10 |
| Style | unwrapStyle | MaxTexturesCount FixedTexelSize AdaptiveTexelSize | MaxTexturesCount |
| Maximal texture count (_relevant for "unwrapStyle=MaxTexturesCount"_) | unwrapMaximalTexCount | number (integer) | 1 |
| Texel size (_relevant for "unwrapStyle=FixedTexelSize"_) | unwrapFixedTexelSizeType | 0 _(Optimal)_ 1 _(2× optimal, 50% texture quality)_ 2 _(4× optimal, 25% texture quality)_ 3 _(10× optimal, 10% texture quality)_ 4 _(100× optimal, 1% texture quality)_ 5 _(Custom)_ | 0 |
| Custom texel size (_relevant for "unwrapStyle=FixedTexelSize" and"unwrapFixedTexelSizeType=5"_) | unwrapFixedTexelSize | number (float) | 0.01 |
| Minimal required texel size (_relevant for "unwrapStyle=AdaptiveTexelSize"_) | unwrapMinTexelSize | 0 _(Optimal)_ 1 _(2× optimal, 50% texture quality)_ 2 _(4× optimal, 25% texture quality)_ 3 _(10× optimal, 10% texture quality)_ 4 _(100× optimal, 1% texture quality)_ 5 _(Custom)_ | 0 |
| Custom minimal required texel size (_relevant for "unwrapStyle=FixedTexelSize" and"unwrapFixedTexelSizeType=5"_) | unwrapMinTexelSize | number (float) | 0.01 |
| Maximal required texel size (_relevant for "unwrapStyle=AdaptiveTexelSize"_) | unwrapMaxTexelSize | 0 _(Optimal)_ 1 _(2× optimal, 50% texture quality)_ 2 _(4× optimal, 25% texture quality)_ 3 _(10× optimal, 10% texture quality)_ 4 _(100× optimal, 1% texture quality)_ 5 _(Custom)_ | 4 |
| Custom maximal required texel size (_relevant for "unwrapStyle=FixedTexelSize" and"unwrapFixedTexelSizeType=5"_) | unwrapMaxTexelSize | number (float) | 10.0 |
| Color & Texture |  |  |  |
| Imported model default texture resolution | txtImportDefaultTexResolution | 512 1024 2048 4096 8192 16384 | 8192 |
| Coloring method | txtMethod | Linear MultiBand | MultiBand |
| Coloring style | colStyle | PhotoConsistencyBased VisibilityBased | VisibilityBased |
| Coloring image layer | ImageLayerForColoring | geometry OR name_of_geometry_layer texture01 OR name_of_texture_layer texture2 OR name_of_texture_layer2 | geometry (if no texture layer is present) texture01 (if texture layer is present) |
| Texturing style | txtStyle | PhotoConsistencyBased VisibilityBased MosaicingBased MaximalIntensity MinimalIntensity AverageIntensity | VisibilityBased |
| Texturing image layer | ImageLayerForTexturing | geometry OR name_of_geometry_layer texture01 OR name_of_texture_layer texture2 OR name_of_texture_layer2 all (_All texturing layers_) | all |
| Downscale images before texturing | txtImageDownscaleTexture | number (integer) | 1 |
| Downscale images before coloring | txtImageDownscaleColor | number (integer) | 2 |
| Fill in uncolored parts | txtFillInUncoloredParts | true false | true |
| Fill in untextured parts | txtFillInUntextoredParts | true false | true |
| Recolor model after texturing | txtRecolorAfterTexturing | true false | true |
| Correct colors | MvsDoCorrectColors | true false | false |
| Ignore color correction | MvsIgnoreCorrectColors | true false | false |
| Prefer 16-bit/HDR texture generation | MvsGeometryTexturingDoHdr | true false | true |

## Error-handling Settings

The following settings allow you to manage potential errors that may occur during command-line processing.

| Name | Key | Value | Default |
| --- | --- | --- | --- |
| Quit on error | appQuitOnError | true false | false |
| Quit on required restart | appQuitOnReset | true false | false |
| Suppress error messages | suppressErrors | true false | false |
| Minimal process duration | appProcessActionTime | number (integer) | 15 |
| Action | appProcessAction | None PlaySound ExecuteProgram | None |
| Command-line process (_relevant for "appProcessAction=ExecuteProgram"_) | appProcessExecCmd | text (string) |  |
