Title: Hardware and Software Requirements | Realityscan Documentation | Epic Developer Community

URL Source: https://dev.epicgames.com/documentation/en-us/realityscan/hardware-and-software-requirements

Markdown Content:
### Requirements

|  |  |
| --- | --- |
| **Operating System** | 64-bit machine |
| **Processor** | Must support 64-bit processing and the AVX2 instruction set |
| **Memory** | At least 8 GB of system RAM |
| **Graphics RAM** | At least 1 GB of VRAM |
| **Graphics Card** | Must support CUDA Compute Capability 3.5 or higher (Compute Capability 6.1 or above is recommended for better performance) |

### Recommendations

RealityScan runs primarily on **Windows**. A **Linux version** is also available, but it is recommended **only for CLI-based workflows**.

We recommend using a machine with at least 4 CPU cores, 16 GB of RAM, and 1024 CUDA cores. To take advantage of the latest improvements in model generation and texturing, we recommend fast NVMe solid-state drives and NVIDIA graphics cards with CUDA Compute Capability 6.1 or higher. While a compatible NVIDIA GPU is recommended for optimal performance, the application can still run and perform image registration without one; however, you won't be able to create models or textures.

The CPU must support at least the SSE4.2 instruction set (Streaming SIMD Extensions 4.2) or a newer version.

To verify CUDA compatibility (CUDA 3.5 or later), ensure your drivers are updated and check the official list on[NVIDIA Developer resources](https://developer.nvidia.com/cuda-gpus).

For Microsoft Windows N editions, the Media Feature Pack must be installed. You can find the appropriate installer here:[Media Feature Pack list for Windows N editions](https://support.microsoft.com/en-us/topic/media-feature-pack-list-for-windows-n-editions-c1c6fffa-d052-8338-7a79-a4bb980a700a). For Windows Server editions, the Media Foundation feature must be enabled.

### Memory Usage

Most processing tasks utilize advanced out-of-core techniques, meaning system RAM is not a performance-limiting factor.

You can register an unlimited number of images or LiDAR scans on a single machine. For example, 16 GB of RAM is typically sufficient for processing thousands of high-resolution images, provided a component workflow is used. This involves separating images into multiple sets, aligning them individually, and merging them into a unified model. For more information on this approach, refer to the application help under the**Component Workflow**topic.

RAM requirements for aligning unregistered image sets depend more on the number of images and features per image than on image resolution. Reducing feature count per image from the default (e.g., 40,000) to a lower value (e.g., 20,000) can double the number of images processed within the same memory limits.

Processes such as meshing, coloring, and texturing are fully out-of-core, so you don't have to worry about RAM. Even with very large datasets (e.g., over a million images or scans), these tasks can be completed effectively on machines with as little as 16 GB of RAM.
