Title: Hardware and Operating System Requirements | Knowledge base

URL Source: https://dev.epicgames.com/community/learning/knowledge-base/DB58/realityscan-hardware-and-operating-system-requirements

Markdown Content:
1.   ![Image 1: Epic Games](https://edc-cdn.net/assets/images/logo-epic.svg)[Developer](https://dev.epicgames.com/)
2.   [Community](https://dev.epicgames.com/community/ "Community")
3.   [RealityScan](https://dev.epicgames.com/community/realityscan "RealityScan")
4.   [Learning](https://dev.epicgames.com/community/realityscan/learning "Learning")
5.   [Epic Games](https://dev.epicgames.com/community/realityscan/learning?source=epic_games "Epic Games")
6.   Hardware and Operating System Requirements

# Hardware and Operating System Requirements

 Hardware and operating system requirements to successfully run RealityScan. 

[![Image 2: Te](https://dev.epicgames.com/community/api/user_profiles/image/808aaf95-e7bf-4a56-a0ef-914f004b7464?resizing_type=fill&width=36&height=36&type=avatar) by MatejKuro](https://dev.epicgames.com/community/profile/kPzlz/kumateCR)Jun 20, 2025•Last Updated:Jul 21, 2025•

Communities RealityScan 

Show more

Knowledge Base 

[Report](https://safety.epicgames.com/policies/reporting-misconduct/submit-report?content_type=learning_post&content_url=https%3A%2F%2Fdev.epicgames.com%2Fcommunity%2Flearning%2Ftutorials%2FDB58%2Frealityscan-hardware-and-operating-system-requirements%3Fcontent_review%3Dtrue&product_id=edc_content_report)

 On this page

1[2 Comments](https://forums.unrealengine.com/t/2567407)11,463 Views

RealityScan requires:

*   a 64-bit machine (CPU must support 64-bit processing and the AVX2 instruction set)

*   at least 8 GB of system RAM

*   a 64-bit version of Windows 10, Windows 11, or Windows Server 2016 or newer

*   an NVIDIA graphics card with at least 1 GB of VRAM

*   the NVIDIA GPU must support CUDA Compute Capability 3.5 or higher (Compute Capability 6.1 or above is recommended for better performance)

*   it is recommended to have the latest version of the NVIDIA graphics driver installed

We recommend using a machine with at least 4 CPU cores, 16 GB of RAM, and 1024 CUDA cores. To take advantage of the latest improvements in model generation and texturing, we recommend fast NVMe solid-state drives and NVIDIA graphics cards with CUDA Compute Capability 6.1 or higher. While a compatible NVIDIA GPU is recommended for optimal performance, the application can still run and perform image registration without one—however, you won't be able to create models or textures.

The CPU must support at least the SSE4.2 instruction set (Streaming SIMD Extensions 4.2) or newer.

To verify CUDA compatibility (CUDA 3.5+), ensure your drivers are updated and check the official list on [NVIDIA Developer resources](https://developer.nvidia.com/cuda-gpus).

For Microsoft Windows N editions, the Media Feature Pack must be installed. You can find the appropriate installer here: [Media Feature Pack list for Windows N editions](https://support.microsoft.com/en-us/topic/media-feature-pack-list-for-windows-n-editions-c1c6fffa-d052-8338-7a79-a4bb980a700a). For Windows Server editions, the Media Foundation feature must be enabled.

#### Memory Usage

Most processing tasks use advanced out-of-core techniques, meaning system RAM is not a limiting factor for performance.

You can register an unlimited number of images or LiDAR scans on a single machine. For example, 16 GB of RAM is typically sufficient for processing thousands of high-resolution images, provided a component workflow is used. This involves separating images into multiple sets, aligning them individually, and merging them into a unified model. More information on this approach can be found in the application help under the **Component Workflow**topic.

RAM requirements for aligning unregistered image sets depend more on the number of images and features per image than on image resolution. Reducing feature count per image from the default (e.g., 40,000) to a lower value (e.g., 20,000) can double the number of images processed within the same memory limits.

Processes such as meshing, coloring, and texturing are fully out-of-core, so you don't have to worry about RAM. Even with very large datasets (e.g., over a million images or scans), these tasks can be completed effectively on machines with as little as 16 GB of RAM.

On this page

*   [Memory Usage](https://dev.epicgames.com/community/learning/knowledge-base/DB58/realityscan-hardware-and-operating-system-requirements#memoryusage)

Recent tutorials

[View all](https://dev.epicgames.com/community/unreal-engine/learning)

[01 - GAS Project Setup - Let's Make a Real Time Strategy C++ Game ![Image 3: Te](https://edc-cdn.net/assets/images/default-user.svg) AlamarsDomain ![Image 4: 01 - GAS Project Setup - Let's Make a Real Time Strategy C++ Game](https://dev.epicgames.com/community/api/learning/image/86ab558f-b2e0-4c15-8120-6c3f6a7d04f7?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/qE1O/unreal-engine-01-gas-project-setup-let-s-make-a-real-time-strategy-c-game)[Save Game в Unreal Engine | сохранение игры ![Image 5: Te](https://dev.epicgames.com/community/api/user_profiles/image/d96078dc-7cf5-4cd1-b60e-216a024caebe?resizing_type=fill&width=36&height=36&type=avatar) ueprosto.ru ![Image 6: Save Game в Unreal Engine | сохранение игры](https://dev.epicgames.com/community/api/learning/image/65962128-70b5-4a3e-ba9f-8e86833d7654?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/dO49/save-game-unreal-engine)[Unreal Engine 6 Mobile Demo | New mobile game made by Unreal Engine 6. This gives a hint of what we could see in in unreal engine 6 and the era of mobile games 2026 ![Image 7: Te](https://dev.epicgames.com/community/api/user_profiles/image/783d3207-f490-47ec-97db-deabf4a4894c?resizing_type=fill&width=36&height=36&type=avatar) Tec Dev Studio ![Image 8: Unreal Engine 6 Mobile Demo | New mobile game made by Unreal Engine 6. This gives a hint of what we could see in in unreal engine 6 and the era of mobile games 2026](https://dev.epicgames.com/community/api/learning/image/7db976bf-b788-423e-aad4-432e5a22b92f?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/Jx7M/unreal-engine-6-mobile-demo-new-mobile-game-made-by-unreal-engine-6-this-gives-a-hint-of-what-we-could-see-in-in-unreal-engine-6-and-the-era-of-mobile-games-2026)[Actor в Unreal Engine | класс Актор ![Image 9: Te](https://dev.epicgames.com/community/api/user_profiles/image/d96078dc-7cf5-4cd1-b60e-216a024caebe?resizing_type=fill&width=36&height=36&type=avatar) ueprosto.ru ![Image 10: Actor в Unreal Engine | класс Актор](https://dev.epicgames.com/community/api/learning/image/41c9f735-a3f7-4e31-938d-965716039c08?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/pYZb/actor-unreal-engine)[Lifecycle в Unreal Engine (жизненный цикл актора) ![Image 11: Te](https://dev.epicgames.com/community/api/user_profiles/image/d96078dc-7cf5-4cd1-b60e-216a024caebe?resizing_type=fill&width=36&height=36&type=avatar) ueprosto.ru ![Image 12: Lifecycle в Unreal Engine (жизненный цикл актора)](https://dev.epicgames.com/community/api/learning/image/3de4a455-586b-4efe-8c4f-37cf1f97c1bb?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/0534/lifecycle-unreal-engine)[Unreal Engine 5.7 - Chaos Destruction for Beginners - Adding Niagara FX ![Image 13: Te](https://dev.epicgames.com/community/api/user_profiles/image/12d81ad4-5643-46ff-ab69-7481fbe525f1?resizing_type=fill&width=36&height=36&type=avatar) John_CTS ![Image 14: Unreal Engine 5.7 - Chaos Destruction for Beginners - Adding Niagara FX](https://dev.epicgames.com/community/api/learning/image/82fd38f6-143b-4bf2-ba91-d9a8b40e881d?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/dOv5/fortnite-fab-unreal-engine-5-7-chaos-destruction-for-beginners-adding-niagara-fx)[Root Component (корневой компонент) в Unreal Engine ![Image 15: Te](https://dev.epicgames.com/community/api/user_profiles/image/d96078dc-7cf5-4cd1-b60e-216a024caebe?resizing_type=fill&width=36&height=36&type=avatar) ueprosto.ru ![Image 16: Root Component (корневой компонент) в Unreal Engine](https://dev.epicgames.com/community/api/learning/image/94689ac7-142a-4f28-a244-e22627bdf401?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/mmpM/root-component-unreal-engine)[UE5 Modular Character Customization ![Image 17: Te](https://dev.epicgames.com/community/api/user_profiles/image/553e6985-234e-460e-8f85-5cbb6a1623fc?resizing_type=fill&width=36&height=36&type=avatar) SirGeo3D ![Image 18: UE5 Modular Character Customization](https://dev.epicgames.com/community/api/learning/image/6bcfc5e5-5c24-4039-8773-3c4366f5d8dc?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/1m68/unreal-engine-ue5-modular-character-customization)[Culling & Occlusion Primer ![Image 19: Te](https://dev.epicgames.com/community/api/user_profiles/image/99d117ae-5aa7-4bc5-8bed-f7c93117f44b?resizing_type=fill&width=36&height=36&type=avatar) braduul ![Image 20: Culling & Occlusion Primer](https://dev.epicgames.com/community/api/learning/image/c17c1104-70f1-4293-9cf2-85edf142d198?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/7OR8/unreal-engine-culling-occlusion-primer)[BugIt, Display "Live" Coordinates, Waypoint Teleport & Play From Camera Location ![Image 21: Te](https://dev.epicgames.com/community/api/user_profiles/image/99d117ae-5aa7-4bc5-8bed-f7c93117f44b?resizing_type=fill&width=36&height=36&type=avatar) braduul ![Image 22: BugIt, Display "Live" Coordinates, Waypoint Teleport & Play From Camera Location](https://dev.epicgames.com/community/api/learning/image/16b9cc94-127e-40a8-b97a-13dad67f242b?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/YoXm/unreal-engine-bugit-display-live-coordinates-waypoint-teleport-play-from-camera-location)[Create & Visualize an Accurate Projectile Trajectory ![Image 23: Te](https://dev.epicgames.com/community/api/user_profiles/image/99d117ae-5aa7-4bc5-8bed-f7c93117f44b?resizing_type=fill&width=36&height=36&type=avatar) braduul ![Image 24: Create & Visualize an Accurate Projectile Trajectory](https://dev.epicgames.com/community/api/learning/image/066e00b3-be0d-48ec-8213-000f89e2048c?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/rvED/unreal-engine-create-visualize-an-accurate-projectile-trajectory)[How to Destroy Stuff with Chaos Physics ![Image 25: Te](https://dev.epicgames.com/community/api/user_profiles/image/99d117ae-5aa7-4bc5-8bed-f7c93117f44b?resizing_type=fill&width=36&height=36&type=avatar) braduul ![Image 26: How to Destroy Stuff with Chaos Physics](https://dev.epicgames.com/community/api/learning/image/5d69fd5a-988e-4e69-8d90-e8c3eaef5fdf?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/jD1V/unreal-engine-how-to-destroy-stuff-with-chaos-physics)[Generating Basic MetaSounds (Pickup, Laser, Explosion Sounds) ![Image 27: Te](https://dev.epicgames.com/community/api/user_profiles/image/99d117ae-5aa7-4bc5-8bed-f7c93117f44b?resizing_type=fill&width=36&height=36&type=avatar) braduul ![Image 28: Generating Basic MetaSounds (Pickup, Laser, Explosion Sounds)](https://dev.epicgames.com/community/api/learning/image/4cc8c313-2fef-4ad5-900b-0f055a3384da?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/bEee/unreal-engine-generating-basic-metasounds-pickup-laser-explosion-sounds)[Project World To Screen & Deproject Screen To World ![Image 29: Te](https://dev.epicgames.com/community/api/user_profiles/image/99d117ae-5aa7-4bc5-8bed-f7c93117f44b?resizing_type=fill&width=36&height=36&type=avatar) braduul ![Image 30: Project World To Screen & Deproject Screen To World](https://dev.epicgames.com/community/api/learning/image/baed3be6-3133-4445-9fda-52855c99dda8?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/alP9/unreal-engine-project-world-to-screen-deproject-screen-to-world)[Move Actors from Afar (No Gizmo) & Avoid Print String Spam ![Image 31: Te](https://dev.epicgames.com/community/api/user_profiles/image/99d117ae-5aa7-4bc5-8bed-f7c93117f44b?resizing_type=fill&width=36&height=36&type=avatar) braduul ![Image 32: Move Actors from Afar (No Gizmo) & Avoid Print String Spam](https://dev.epicgames.com/community/api/learning/image/32ad4b8f-6574-4de8-916f-75cc545e722f?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/Z14B/unreal-engine-move-actors-from-afar-no-gizmo-avoid-print-string-spam)[Flow Control Basics & Nameless Execution Pins ![Image 33: Te](https://dev.epicgames.com/community/api/user_profiles/image/99d117ae-5aa7-4bc5-8bed-f7c93117f44b?resizing_type=fill&width=36&height=36&type=avatar) braduul ![Image 34: Flow Control Basics & Nameless Execution Pins](https://dev.epicgames.com/community/api/learning/image/a0454ef8-4fd6-4b1f-9d66-34326fa470de?resizing_type=fit&width=160&height=160)](https://dev.epicgames.com/community/learning/tutorials/JxEM/unreal-engine-flow-control-basics-nameless-execution-pins)
