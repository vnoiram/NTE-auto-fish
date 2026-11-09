# Changelog

## [0.11.0](https://github.com/vnoiram/NTE-auto-fish/compare/v0.10.0...v0.11.0) (2026-11-09)


### Features

* add application and documentation icons ([abe4c81](https://github.com/vnoiram/NTE-auto-fish/commit/abe4c8130db63f086189fd2f7657ff6c8e08fb2d))
* add CLI config commands, auto-install deps, and remove template matching from docs ([25eac50](https://github.com/vnoiram/NTE-auto-fish/commit/25eac508fa4544096b903a8d7f770d17cd5f96b6))
* add GitHub Actions workflow to build and release Windows executables ([f5cf1b1](https://github.com/vnoiram/NTE-auto-fish/commit/f5cf1b19db5acec4a272f6c3d65f8b2fe1392c2b))
* add humanization layer with configurable natural variation ([933fc95](https://github.com/vnoiram/NTE-auto-fish/commit/933fc95ca748de1e3125c36993ef2b5f44cf41ab)), closes [#9](https://github.com/vnoiram/NTE-auto-fish/issues/9)
* add responsive UI scaling for different screen resolutions ([53adb79](https://github.com/vnoiram/NTE-auto-fish/commit/53adb799de5055b87dfb81449ef9ca1935a6a033))
* **build:** bundle templates into EXE and simplify calibration ([8bb8654](https://github.com/vnoiram/NTE-auto-fish/commit/8bb8654006c5894a58e35125590304c3310ede2b))
* change icon ([1ffe9b7](https://github.com/vnoiram/NTE-auto-fish/commit/1ffe9b70b269738ff689cbf73213f56ef208ffca))
* embed admin elevation manifest in GUI exe ([b166e61](https://github.com/vnoiram/NTE-auto-fish/commit/b166e61ffd189ccda02ea94b2846e6d1732df87c))
* embed version from version.txt in build artifacts and window title ([aab4b82](https://github.com/vnoiram/NTE-auto-fish/commit/aab4b82f6ec3f081d43d3f0e1b6befddb6994d63))
* Enhance CI workflows, improve logging, and add unit tests ([#36](https://github.com/vnoiram/NTE-auto-fish/issues/36)) ([bfb130d](https://github.com/vnoiram/NTE-auto-fish/commit/bfb130de07cd31ad4ef704b7d7c33ff644445f44))
* Enhance configuration and GUI for improved usability and performance ([0090a64](https://github.com/vnoiram/NTE-auto-fish/commit/0090a6436aa9d793688eb9e0f159e57929570448))
* **gui:** add system settings panel with update checker ([1171d6b](https://github.com/vnoiram/NTE-auto-fish/commit/1171d6bbc1f16983250a921ee45e0126f005193e))
* **humanization:** implement humanized mouse movement and reaction latency ([d2ff4bd](https://github.com/vnoiram/NTE-auto-fish/commit/d2ff4bd23491e026dce3089d393a4854dbb456d1))
* implement adaptive humanization for improved tracking responsiveness ([75abdc7](https://github.com/vnoiram/NTE-auto-fish/commit/75abdc7174b57a88d0245bbb4b71dffa2bf20b1f))
* **input:** humanize cursor movement profiles ([87789b5](https://github.com/vnoiram/NTE-auto-fish/commit/87789b56a11262b85369f21d12b134cb5c3fc706))
* per-session fish catch logging (CSV/JSON/XLSX export) ([#52](https://github.com/vnoiram/NTE-auto-fish/issues/52)) ([28897d1](https://github.com/vnoiram/NTE-auto-fish/commit/28897d1cc1ad2216cfedce9c16be297e9db06aaa))
* **ui:** add English and Japanese language selection ([075fdd4](https://github.com/vnoiram/NTE-auto-fish/commit/075fdd4ef2b99d736d73f6b0a4c8cff793af2389))
* **vision:** add adaptive resolution scaling for vision thresholds ([7a6e9b1](https://github.com/vnoiram/NTE-auto-fish/commit/7a6e9b140f89322029ce66950b6ac71a7c538f9b))
* **vision:** add configurable detection threshold to fix cursor detection issues ([255145c](https://github.com/vnoiram/NTE-auto-fish/commit/255145c01324b511968a489492d95b9435b71eb8)), closes [#26](https://github.com/vnoiram/NTE-auto-fish/issues/26)
* 优化 PID 算法，添加已知问题文档 ([a56b2af](https://github.com/vnoiram/NTE-auto-fish/commit/a56b2af771697e926e9584be5d299b033eb41346))
* 更新构建配置以排除不必要的模块并调整工件上传名称 ([a087968](https://github.com/vnoiram/NTE-auto-fish/commit/a0879682f49138636db463c0653d1649c7a9184f))
* 更新构建配置以支持单文件打包和调整上传路径，更新文档以反映新特性 ([834b5c2](https://github.com/vnoiram/NTE-auto-fish/commit/834b5c238358313d909f27aa86950455b9bc9806))
* 更新构建配置和文档，添加调试模式选项 ([ec7c833](https://github.com/vnoiram/NTE-auto-fish/commit/ec7c83354b3d678b6e3be8e56daba5a28be82869))
* 添加 MIT 许可证，更新 README 文档，优化 GUI 和配置，增强高 DPI 支持 ([880e86e](https://github.com/vnoiram/NTE-auto-fish/commit/880e86e98f3de8598d2ebc30e65cdd36436378b5))
* 添加.gitkeep文件以确保模板目录被Git跟踪 ([0de079c](https://github.com/vnoiram/NTE-auto-fish/commit/0de079c414d1c5bf68d90b62e8a502393a0a1385))
* 添加热键配置和相关功能，更新设置面板以支持热键自定义 ([88d9e3f](https://github.com/vnoiram/NTE-auto-fish/commit/88d9e3ff4e33ab172d2725b7039e26507937d2e8))
* 添加重置默认值功能，更新设置面板以支持配置重置 ([806088f](https://github.com/vnoiram/NTE-auto-fish/commit/806088f9e776877b399b00efc4b8c14a80e04a90))


### Bug Fixes

* apply monitor offset to ROIs for correct multi-monitor coordinates ([cd37599](https://github.com/vnoiram/NTE-auto-fish/commit/cd37599e832d0169822ed6aa6e8cce895671ba1a)), closes [#13](https://github.com/vnoiram/NTE-auto-fish/issues/13)
* **bot:** add fallback to dismiss result screen on consecutive wait timeouts ([d386728](https://github.com/vnoiram/NTE-auto-fish/commit/d386728c1d2fcb7f10730248848012fdfa056415)), closes [#20](https://github.com/vnoiram/NTE-auto-fish/issues/20)
* **build:** embed version.txt in artifacts to resolve 0.0.0 window title ([0904fab](https://github.com/vnoiram/NTE-auto-fish/commit/0904fab8da946d34921d0390a1112daf6a437c04))
* **build:** include assets directory in PyInstaller bundle ([1ddaa9e](https://github.com/vnoiram/NTE-auto-fish/commit/1ddaa9e6edd989650a4260a64a9591350ccf0099))
* check error dialog immediately after cast instead of after full animation delay ([ebd5e77](https://github.com/vnoiram/NTE-auto-fish/commit/ebd5e772486f23f69deb13fef64a1a11f8e586ce))
* **ci:** use default token for release please ([71b1f5b](https://github.com/vnoiram/NTE-auto-fish/commit/71b1f5bb9e36ee19cd8aa7bbc57fbf981406041f))
* **ci:** use PowerShell Compress-Archive instead of zip for CLI packaging ([41ad48b](https://github.com/vnoiram/NTE-auto-fish/commit/41ad48be98279f96e77ec1e478fd6e8e36d985d7))
* **config:** perform in-place update during settings reset ([5ded579](https://github.com/vnoiram/NTE-auto-fish/commit/5ded579e9fc90b5825d9a19da8d1f339aea55f62))
* **core:** throttle GUI loop and handle capture crash on startup ([#30](https://github.com/vnoiram/NTE-auto-fish/issues/30)) ([b1c8f41](https://github.com/vnoiram/NTE-auto-fish/commit/b1c8f415232e8e993266445bb50dd63a13696f3b))
* correct DPG callback arg count for category button ([7821698](https://github.com/vnoiram/NTE-auto-fish/commit/7821698d31c5a1f3d2e57bd619803ba7e34389b1))
* detect fish-escape error dialog at start of RESULT before it auto-dismisses ([44e959e](https://github.com/vnoiram/NTE-auto-fish/commit/44e959ed2930ec137408c5c2d3dde0e1b55d779d))
* **gui:** add application icon to the window viewport ([4d83d23](https://github.com/vnoiram/NTE-auto-fish/commit/4d83d23b4d676fa5d10ed4d1141425431aab0834))
* **gui:** correct viewport API and add GitHub links ([81757e1](https://github.com/vnoiram/NTE-auto-fish/commit/81757e1c9c964598d55c6d7922ec762cdb7fa20a))
* **gui:** resolve settings slider occlusion and add unit suffixes ([f1afa29](https://github.com/vnoiram/NTE-auto-fish/commit/f1afa2916800d0cbaf9c8b23840c4284f19b87ac))
* **gui:** support Dear PyGui 2.3.1 ([0d02e0f](https://github.com/vnoiram/NTE-auto-fish/commit/0d02e0fb4888592f517b38e40c1d6cee539c2947))
* **gui:** use bundled VERSION for update checking ([3ca459d](https://github.com/vnoiram/NTE-auto-fish/commit/3ca459d76cc60c95449a8f3d9ec05a2ef940c570))
* harden imports, config, logging, and thread safety ([e69fe4e](https://github.com/vnoiram/NTE-auto-fish/commit/e69fe4e038affce0f9ca1a75b2122593ec613954))
* harden OCR init, session manager locking and frozen build ([55d51c8](https://github.com/vnoiram/NTE-auto-fish/commit/55d51c89cf823b500aae0e6ece7938cfb5fdf154))
* increase result_wait_secs default from 2.2s to 3.0s ([9b7c30e](https://github.com/vnoiram/NTE-auto-fish/commit/9b7c30e49c10140f97495650753bf22e636840a1)), closes [#8](https://github.com/vnoiram/NTE-auto-fish/issues/8)
* **logic:** implement false hook detection to prevent menu opening loop ([0dee473](https://github.com/vnoiram/NTE-auto-fish/commit/0dee47329477fc4fa57631f2485a05a4f3877da2)), closes [#27](https://github.com/vnoiram/NTE-auto-fish/issues/27)
* make pulse_hold stop-aware and harden sample_reaction ([c6ad421](https://github.com/vnoiram/NTE-auto-fish/commit/c6ad421b07838b88d116e5a553175039d6dbdd26))
* **ocr:** migrate to RapidOCR 3 ([1ae3223](https://github.com/vnoiram/NTE-auto-fish/commit/1ae322336c18ec3522a2d0e037d8f15ca254be21))
* raise error detection brightness threshold to reduce nighttime false positives ([865d1d3](https://github.com/vnoiram/NTE-auto-fish/commit/865d1d397d570461e2b361d051bbb96366253d6e))
* rename calibration log to avoid false error coloring in GUI ([d4b1861](https://github.com/vnoiram/NTE-auto-fish/commit/d4b1861e5c4ccb935c700470f1cd46c39ba35e94))
* reset error counter on resume and remove duplicate main-loop error check ([f9b9c96](https://github.com/vnoiram/NTE-auto-fish/commit/f9b9c96669d09eb58553f6f050cf450eab43cd9a))
* resolve settings NameError, bot lifecycle, and HSV limit bugs ([fe1a3c5](https://github.com/vnoiram/NTE-auto-fish/commit/fe1a3c53a932fb294a420e1b835ad0c90f1ea486))
* run error dialog detection in WAITING state to catch no-bait errors ([6b300bc](https://github.com/vnoiram/NTE-auto-fish/commit/6b300bc98a768637c91929ea7a904b59ba87f570))
* scale min_area by screen resolution to fix cursor detection at 1080p/720p ([3c8c970](https://github.com/vnoiram/NTE-auto-fish/commit/3c8c970a01f8660ecf4cbfae666861e0812d31a8))
* validate settings, survive capture errors and tighten exports ([fb7c28d](https://github.com/vnoiram/NTE-auto-fish/commit/fb7c28d9be7a8cc688d35fc0c4ab330980445e4a))
* **vision:** lower minimum area threshold for HSV detection to support 1080p ([2f467d4](https://github.com/vnoiram/NTE-auto-fish/commit/2f467d46250f9f53f1a6ba15efb712e821e8b726))
* **vision:** optimize error dialog detection thresholds and fix parameter scaling ([2abd34d](https://github.com/vnoiram/NTE-auto-fish/commit/2abd34ddd5897f5b4ee198399857400aa27c2665))
* 全局 bar 检测优先级最高，所有状态检测到 bar 元素立即进入 STRUGGLING ([0f58cc2](https://github.com/vnoiram/NTE-auto-fish/commit/0f58cc205f61f7fd8caa2038f591643eaf955a72))
* 收紧错误检测条件，调整 kd 默认值 ([5fa25a6](https://github.com/vnoiram/NTE-auto-fish/commit/5fa25a62c6c1711f152231550bb3f9acaad8ba30))
* 改进鱼类捕捉状态监测 ([38ff8f0](https://github.com/vnoiram/NTE-auto-fish/commit/38ff8f00848321bfcbb01fe98a1d6731cc2f33e3))
* 错误检测仅在 IDLE/WAITING 状态运行，避免打断 STRUGGLING 追踪 ([8867b0e](https://github.com/vnoiram/NTE-auto-fish/commit/8867b0e2b63fbd326f087de587ae786adc1f7adf))


### Performance Improvements

* optimize vision processing and debug logging I/O ([b6ad126](https://github.com/vnoiram/NTE-auto-fish/commit/b6ad12670fefb6f015e5425348ab3b4e4a298a47))

## [0.10.0](https://github.com/Chizukuo/NTE-auto-fish/compare/v0.9.0...v0.10.0) (2026-06-12)


### Features

* per-session fish catch logging (CSV/JSON/XLSX export) ([#52](https://github.com/Chizukuo/NTE-auto-fish/issues/52)) ([28897d1](https://github.com/Chizukuo/NTE-auto-fish/commit/28897d1cc1ad2216cfedce9c16be297e9db06aaa))

## [0.9.0](https://github.com/Chizukuo/NTE-auto-fish/compare/v0.8.0...v0.9.0) (2026-05-20)


### Features

* Enhance CI workflows, improve logging, and add unit tests ([#36](https://github.com/Chizukuo/NTE-auto-fish/issues/36)) ([bfb130d](https://github.com/Chizukuo/NTE-auto-fish/commit/bfb130de07cd31ad4ef704b7d7c33ff644445f44))


### Bug Fixes

* **core:** throttle GUI loop and handle capture crash on startup ([#30](https://github.com/Chizukuo/NTE-auto-fish/issues/30)) ([b1c8f41](https://github.com/Chizukuo/NTE-auto-fish/commit/b1c8f415232e8e993266445bb50dd63a13696f3b))
* resolve settings NameError, bot lifecycle, and HSV limit bugs ([fe1a3c5](https://github.com/Chizukuo/NTE-auto-fish/commit/fe1a3c53a932fb294a420e1b835ad0c90f1ea486))

## [0.8.0](https://github.com/Chizukuo/NTE-auto-fish/compare/v0.7.2...v0.8.0) (2026-05-16)


### Features

* **humanization:** implement humanized mouse movement and reaction latency ([d2ff4bd](https://github.com/Chizukuo/NTE-auto-fish/commit/d2ff4bd23491e026dce3089d393a4854dbb456d1))
* **vision:** add configurable detection threshold to fix cursor detection issues ([255145c](https://github.com/Chizukuo/NTE-auto-fish/commit/255145c01324b511968a489492d95b9435b71eb8)), closes [#26](https://github.com/Chizukuo/NTE-auto-fish/issues/26)


### Bug Fixes

* **logic:** implement false hook detection to prevent menu opening loop ([0dee473](https://github.com/Chizukuo/NTE-auto-fish/commit/0dee47329477fc4fa57631f2485a05a4f3877da2)), closes [#27](https://github.com/Chizukuo/NTE-auto-fish/issues/27)
* **vision:** optimize error dialog detection thresholds and fix parameter scaling ([2abd34d](https://github.com/Chizukuo/NTE-auto-fish/commit/2abd34ddd5897f5b4ee198399857400aa27c2665))


### Performance Improvements

* optimize vision processing and debug logging I/O ([b6ad126](https://github.com/Chizukuo/NTE-auto-fish/commit/b6ad12670fefb6f015e5425348ab3b4e4a298a47))

## [0.7.2](https://github.com/Chizukuo/NTE-auto-fish/compare/v0.7.1...v0.7.2) (2026-05-15)


### Bug Fixes

* **build:** include assets directory in PyInstaller bundle ([1ddaa9e](https://github.com/Chizukuo/NTE-auto-fish/commit/1ddaa9e6edd989650a4260a64a9591350ccf0099))
* **config:** perform in-place update during settings reset ([5ded579](https://github.com/Chizukuo/NTE-auto-fish/commit/5ded579e9fc90b5825d9a19da8d1f339aea55f62))
* **gui:** add application icon to the window viewport ([4d83d23](https://github.com/Chizukuo/NTE-auto-fish/commit/4d83d23b4d676fa5d10ed4d1141425431aab0834))
* **gui:** correct viewport API and add GitHub links ([81757e1](https://github.com/Chizukuo/NTE-auto-fish/commit/81757e1c9c964598d55c6d7922ec762cdb7fa20a))

## [0.7.1](https://github.com/Chizukuo/NTE-auto-fish/compare/v0.7.0...v0.7.1) (2026-05-13)


### Bug Fixes

* **bot:** add fallback to dismiss result screen on consecutive wait timeouts ([d386728](https://github.com/Chizukuo/NTE-auto-fish/commit/d386728c1d2fcb7f10730248848012fdfa056415)), closes [#20](https://github.com/Chizukuo/NTE-auto-fish/issues/20)
* **gui:** use bundled VERSION for update checking ([3ca459d](https://github.com/Chizukuo/NTE-auto-fish/commit/3ca459d76cc60c95449a8f3d9ec05a2ef940c570))

## [0.7.0](https://github.com/Chizukuo/NTE-auto-fish/compare/v0.6.1...v0.7.0) (2026-05-12)


### Features

* add application and documentation icons ([abe4c81](https://github.com/Chizukuo/NTE-auto-fish/commit/abe4c8130db63f086189fd2f7657ff6c8e08fb2d))
* **gui:** add system settings panel with update checker ([1171d6b](https://github.com/Chizukuo/NTE-auto-fish/commit/1171d6bbc1f16983250a921ee45e0126f005193e))
* implement adaptive humanization for improved tracking responsiveness ([75abdc7](https://github.com/Chizukuo/NTE-auto-fish/commit/75abdc7174b57a88d0245bbb4b71dffa2bf20b1f))
* **vision:** add adaptive resolution scaling for vision thresholds ([7a6e9b1](https://github.com/Chizukuo/NTE-auto-fish/commit/7a6e9b140f89322029ce66950b6ac71a7c538f9b))


### Bug Fixes

* **gui:** resolve settings slider occlusion and add unit suffixes ([f1afa29](https://github.com/Chizukuo/NTE-auto-fish/commit/f1afa2916800d0cbaf9c8b23840c4284f19b87ac))
* **vision:** lower minimum area threshold for HSV detection to support 1080p ([2f467d4](https://github.com/Chizukuo/NTE-auto-fish/commit/2f467d46250f9f53f1a6ba15efb712e821e8b726))

## [0.6.1](https://github.com/Chizukuo/NTE-auto-fish/compare/v0.6.0...v0.6.1) (2026-05-10)


### Bug Fixes

* **build:** embed version.txt in artifacts to resolve 0.0.0 window title ([0904fab](https://github.com/Chizukuo/NTE-auto-fish/commit/0904fab8da946d34921d0390a1112daf6a437c04))

## [0.6.0](https://github.com/Chizukuo/NTE-auto-fish/compare/v0.5.0...v0.6.0) (2026-05-10)


### Features

* add humanization layer with configurable natural variation ([933fc95](https://github.com/Chizukuo/NTE-auto-fish/commit/933fc95ca748de1e3125c36993ef2b5f44cf41ab)), closes [#9](https://github.com/Chizukuo/NTE-auto-fish/issues/9)
* embed admin elevation manifest in GUI exe ([b166e61](https://github.com/Chizukuo/NTE-auto-fish/commit/b166e61ffd189ccda02ea94b2846e6d1732df87c))
* embed version from version.txt in build artifacts and window title ([aab4b82](https://github.com/Chizukuo/NTE-auto-fish/commit/aab4b82f6ec3f081d43d3f0e1b6befddb6994d63))


### Bug Fixes

* apply monitor offset to ROIs for correct multi-monitor coordinates ([cd37599](https://github.com/Chizukuo/NTE-auto-fish/commit/cd37599e832d0169822ed6aa6e8cce895671ba1a)), closes [#13](https://github.com/Chizukuo/NTE-auto-fish/issues/13)
* correct DPG callback arg count for category button ([7821698](https://github.com/Chizukuo/NTE-auto-fish/commit/7821698d31c5a1f3d2e57bd619803ba7e34389b1))
* harden imports, config, logging, and thread safety ([e69fe4e](https://github.com/Chizukuo/NTE-auto-fish/commit/e69fe4e038affce0f9ca1a75b2122593ec613954))
* increase result_wait_secs default from 2.2s to 3.0s ([9b7c30e](https://github.com/Chizukuo/NTE-auto-fish/commit/9b7c30e49c10140f97495650753bf22e636840a1)), closes [#8](https://github.com/Chizukuo/NTE-auto-fish/issues/8)
* make pulse_hold stop-aware and harden sample_reaction ([c6ad421](https://github.com/Chizukuo/NTE-auto-fish/commit/c6ad421b07838b88d116e5a553175039d6dbdd26))
* rename calibration log to avoid false error coloring in GUI ([d4b1861](https://github.com/Chizukuo/NTE-auto-fish/commit/d4b1861e5c4ccb935c700470f1cd46c39ba35e94))

## [0.5.0](https://github.com/Chizukuo/NTE-auto-fish/compare/v0.4.2...v0.5.0) (2026-05-08)


### Features

* add CLI config commands, auto-install deps, and remove template matching from docs ([25eac50](https://github.com/Chizukuo/NTE-auto-fish/commit/25eac508fa4544096b903a8d7f770d17cd5f96b6))
* add responsive UI scaling for different screen resolutions ([53adb79](https://github.com/Chizukuo/NTE-auto-fish/commit/53adb799de5055b87dfb81449ef9ca1935a6a033))


### Bug Fixes

* check error dialog immediately after cast instead of after full animation delay ([ebd5e77](https://github.com/Chizukuo/NTE-auto-fish/commit/ebd5e772486f23f69deb13fef64a1a11f8e586ce))
* **ci:** use PowerShell Compress-Archive instead of zip for CLI packaging ([41ad48b](https://github.com/Chizukuo/NTE-auto-fish/commit/41ad48be98279f96e77ec1e478fd6e8e36d985d7))
* raise error detection brightness threshold to reduce nighttime false positives ([865d1d3](https://github.com/Chizukuo/NTE-auto-fish/commit/865d1d397d570461e2b361d051bbb96366253d6e))
* run error dialog detection in WAITING state to catch no-bait errors ([6b300bc](https://github.com/Chizukuo/NTE-auto-fish/commit/6b300bc98a768637c91929ea7a904b59ba87f570))
* fix multi-monitor calibration for screen capture and ROI detection ([#7](https://github.com/Chizukuo/NTE-auto-fish/pull/7))
* improve default HSV config detection accuracy for sunset and blue-water conditions ([#5](https://github.com/Chizukuo/NTE-auto-fish/pull/5))
