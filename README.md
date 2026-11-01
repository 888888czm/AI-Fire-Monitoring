# MIT License

Copyright (c) 2026 <蔡梓铭>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

# 法律声明与免责声明

**本项目名称：LifeGuard Monitor（生命危险行为监控系统）**
**版权持有人：<蔡梓铭>**
**首次发布年份：2026**

## 一、法律声明

### 1. 著作权归属

本项目的源代码、文档及相关文件（以下统称“本软件”）的著作权归版权持有人所有，受《中华人民共和国著作权法》《计算机软件保护条例》及国际著作权公约保护。本软件以 MIT 许可证开源发布，任何个人或组织在遵守 MIT 许可证条款的前提下，可自由使用、复制、修改、合并、发布、分发、再许可及销售本软件的副本。

### 2. 开源许可的效力

MIT 许可证是附条件的著作权许可合同。使用者下载、安装、使用、修改或分发本软件，即视为接受 MIT 许可证的全部条款。使用者分发本软件或其衍生作品时，必须保留上述版权声明和许可声明。

### 3. 商标与名称

本项目的名称“LifeGuard Monitor”及版权持有人的姓名/笔名，未经书面许可，不得用于暗示对本软件衍生作品的官方认可或背书。

### 4. 第三方依赖

本软件依赖以下第三方开源组件，它们各自受其原始许可证约束，与本项目的 MIT 许可证相互独立：

| 组件                     | 许可证                                |
| ---------------------- | ---------------------------------- |
| OpenCV (opencv-python) | Apache License 2.0                 |
| MediaPipe              | Apache License 2.0                 |
| Pillow                 | HPND License                       |
| NumPy                  | BSD 3-Clause License               |
| Requests               | Apache License 2.0                 |
| Tkinter                | Python Software Foundation License |

使用者应自行遵守上述第三方组件的许可证条款。

### 5. 使用场景的合法性

本软件涉及摄像头图像采集、行为分析、地理位置获取和第三方消息推送功能。使用者在使用本软件时，必须遵守《中华人民共和国个人信息保护法》《中华人民共和国网络安全法》《公共安全视频图像信息系统管理条例》等适用法律法规。使用者应确保：

- 摄像头安装和拍摄范围限于自己有权控制的场所，不得拍摄他人私密空间或侵犯他人隐私；
- 不得将本软件用于偷拍、窥视、跟踪、骚扰或其他违法用途；
- 不得未经他人同意收集、存储、传播他人的影像、位置等个人信息；
- 在公共场所或涉及他人影像的场景中使用时，应遵守当地关于视频监控的备案、标识和告知要求。

因使用者违反上述规定而产生的任何法律责任，由使用者自行承担。

## 二、免责声明

### 1. “按原样”提供

本软件按“原样”（AS IS）提供，不附带任何明示或默示的保证，包括但不限于对适销性、特定用途适用性、准确性、不侵权的保证。版权持有人不对本软件的功能完整性、运行稳定性、检测准确性作出任何承诺。

### 2. 非安防、非医疗设备

本软件是**辅助提醒工具**，**不是安防设备、消防设备或医疗监护设备**。其火焰/烟雾检测基于颜色阈值，姿态检测基于几何规则，存在误报和漏报的可能。本软件**不能替代**专业火灾报警系统、跌倒监测设备、医疗监护仪器或人工值守。使用者不得将本软件作为生命安全保障的唯一手段。

### 3. 检测结果的局限性

- 火焰检测可能受灯光、夕阳、橙色物体、反光等因素干扰而误报；
- 烟雾检测可能受浅色墙面、衣物、蒸汽等干扰；
- 姿态检测可能对坐姿、弯腰、蹲下等正常动作产生漏报或误报，也可能因遮挡、光线不足而无法识别；
- 地理位置基于 IP 定位，精度有限，可能与实际位置存在偏差；
- 微信推送依赖第三方服务（Server酱），可能因网络、额度、服务变更等原因失败或延迟。

使用者应理解上述局限，并对检测结果进行人工核实。

### 4. 责任限制

在适用法律允许的最大范围内，版权持有人不对因使用或无法使用本软件而产生的任何直接、间接、偶然、特殊、惩罚性或后果性损害承担责任，包括但不限于人身伤害、财产损失、数据丢失、业务中断、利润损失或第三方索赔，无论该损害是否基于合同、侵权、严格责任或其他法律理论，也无论版权持有人是否已被告知此类损害的可能性。

### 5. 使用者责任

使用者应自行评估本软件是否适合其使用场景，自行承担使用本软件的全部风险。使用者应自行负责本软件的部署、配置、测试、维护和监控，并自行确保其使用行为符合所在地法律法规。

### 6. 无持续维护义务

版权持有人没有义务为本软件提供更新、修复、技术支持或安全补丁。本软件可能随时变更或停止维护，恕不另行通知。

## 三、适用法律与争议解决

本声明及 MIT 许可证的解释与适用，以中华人民共和国法律为准（不含冲突法规则）。因本软件产生的争议，双方应友好协商解决；协商不成的，提交版权持有人住所地有管辖权的人民法院诉讼解决。

## 四、声明的可分割性

本声明任何条款被认定为无效或不可执行的，不影响其余条款的效力。该无效条款应在最大范围内被解释为符合其原意的有效条款。
## 五 快速使用
Windows用户直接点击AI-Fire-Monitoring.py文件（用Python/Pycharm打开）即可，可以用它生成.exe文件再运行即可。

---

**最后更新：2026 年**

**如对本声明有疑问，请通过项目仓库的 Issue 或版权持有人公开的联系方式沟通。**
