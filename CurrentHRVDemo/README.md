# 此在 / Current — HRV Δ 采集骨架

一个 iOS App，跑通「到访前测一次 → 到访后测一次 → 只存 Δ」的完整链路。
不需要 Watch App。

## 一、装配（约 5 分钟）

本仓库只有源码，没有 `.xcodeproj`——手写的工程文件一旦有一个字节错就打不开，
用 Xcode 自己生成的更稳。

1. Xcode → File → New → Project → **iOS / App**
2. Product Name: `CurrentHRVDemo`，Interface: **SwiftUI**，Language: **Swift**
3. 建好后，把 `Sources/` 里的 5 个 `.swift` 全选拖进 Xcode 的项目导航器，
   勾选 **Copy items if needed** + 你的 target。
   拖进去后**删掉 Xcode 自动生成的 `ContentView.swift` 和 `CurrentHRVDemoApp.swift`**
   （或者反过来，用本仓库的覆盖它们），避免 `@main` 重复。
4. 选中 target → **Signing & Capabilities** → `+ Capability` → **HealthKit**
   （不要勾 Clinical Health Records / Background Delivery，这个骨架用不上）
5. 选中 target → **Info** 标签页 → 加两行：

   | Key | Value |
   |---|---|
   | `Privacy - Health Share Usage Description` | 用于读取你的心率变异性，计算到访空间前后的变化 |
   | `Privacy - Health Update Usage Description` | 仅用于在模拟器中写入演示样本 |

   等价的 Build Settings 写法：
   `INFOPLIST_KEY_NSHealthShareUsageDescription` / `INFOPLIST_KEY_NSHealthUpdateUsageDescription`

   > 少了 Share 那条会直接崩在 `requestAuthorization`，这是最常见的翻车点。

6. Run。

## 二、模拟器上到底能跑到哪一步

| | iOS 模拟器 | 真机 + Apple Watch |
|---|---|---|
| App 启动、HealthKit 可用 | ✅ | ✅ |
| 系统授权弹窗 | ✅ | ✅ |
| 手表写入的真实 HRV | ❌ 一条都没有 | ✅ |
| 演示模式（App 自己写合成样本） | ✅ 全链路可演示 | ✅（记得关掉） |

**watchOS 模拟器在这件事上帮不上忙**：配对的 watch/iPhone 模拟器之间不同步
HealthKit 数据，模拟器也没有真实传感器，watchOS 的「正念」跑完不会产生 SDNN。
所以这个骨架是纯 iOS target，不建 Watch target。

界面上的「模拟器演示模式」开关就是为此存在：它让 App 用 `HKHealthStore.save()`
写一条合成 SDNN 再读回来，把授权 → 查询 → 计算 Δ → 生成上传体这条链路完整走一遍。
合成样本的 `sourceRevision.source` 是本 App，`SDNNReading.isSynthetic` 会标出来，
真机统计时按这个字段剔除。

## 三、代码里已经处理掉的几个坑

- **读权限不可见**：`authorizationStatus(for:)` 只反映写权限。被拒绝时查询返回空数组，
  和「真的没数据」无法区分，所以文案写的是「读不到，可能是同步延迟或没授权」，
  不是「暂无数据」。
- **Swift 6 严格并发**：`HKQuantitySample` 是非 Sendable 的 class，不能跨
  continuation 边界传。查询回调里就地取值，转成 `SDNNReading` 这个 Sendable 结构体。
- **步行污染**：`VisitDelta.make` 会拉取两次采样之间的步数，判定 `ActivityLevel`，
  `exercise` 直接把置信度降级。不修正的话，所有需要走路到达的空间都会被系统性打成负面。
- **绝对值不可跨人比较**：存的是 `ln(after) − ln(before)`，不是 `after − before`。
- **只上传 Δ**：`VisitDelta.uploadPayload` 明确列出离开设备的字段，
  个人基线 `localBaselineSDNN` 只留在本地。界面上会把这个 JSON 直接显示出来。

## 四、真机演示前

- 提前 48 小时开始用手表攒真实数据，别指望现场做两次呼吸就有 Δ。
- 手表 → iPhone 的 HealthKit 同步有几分钟延迟，读不到就等一会儿再点一次。
- 第三方 App 没有公开 API 能深链到 watchOS 的「正念」，这一步只能靠文案引导用户自己操作。
