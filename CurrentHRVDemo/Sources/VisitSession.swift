import Foundation
import SwiftUI

@MainActor
final class VisitSession: ObservableObject {

    enum Stage: Equatable {
        case needsAuthorization
        case readyForBefore
        case atSpace          // 已有 before，等 after
        case done
    }

    @Published private(set) var stage: Stage = .needsAuthorization
    @Published private(set) var before: SDNNReading?
    @Published private(set) var after: SDNNReading?
    @Published private(set) var result: VisitDelta?
    @Published private(set) var baseline: Double?
    @Published var subjectiveDelta: Int = 0
    @Published var spaceID: String = "space_lakeside_bench_01"
    @Published var statusMessage: String = ""
    @Published var errorMessage: String?

    let health = HealthKitService()

    func authorize() async {
        do {
            try await health.requestAuthorization()
            stage = .readyForBefore
            baseline = try? await health.personalBaseline()
            statusMessage = baseline.map { String(format: "个人基线 %.0f ms（近 14 天中位数）", $0) }
                ?? "还没有足够的历史数据来算基线"
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// 读「到访前」那条。窗口取最近 15 分钟——正念呼吸刚结束的那条应该落在里面。
    func captureBefore() async {
        await capture(isBefore: true)
    }

    func captureAfter() async {
        await capture(isBefore: false)
    }

    private func capture(isBefore: Bool) async {
        errorMessage = nil
        let end = Date()
        let start = end.addingTimeInterval(-15 * 60)
        do {
            let reading = try await health.latestSDNN(from: start, to: end)
            if isBefore {
                before = reading
                stage = .atSpace
                statusMessage = "到访前已记录。到店后先静坐 3–5 分钟，再做第二次呼吸。"
            } else {
                after = reading
                await finish(after: reading)
            }
        } catch {
            errorMessage = "\(error.localizedDescription)\n手表同步有延迟，通常要等几分钟；也可能是读权限没给。"
        }
    }

    private func finish(after reading: SDNNReading) async {
        guard let before else { return }
        let steps = await health.stepCount(from: before.endDate, to: reading.endDate)
        let delta = VisitDelta.make(spaceID: spaceID,
                                    before: before,
                                    after: reading,
                                    preActivity: .from(steps: steps),
                                    subjectiveDelta: subjectiveDelta,
                                    baseline: baseline)
        result = delta
        stage = .done
        statusMessage = String(format: "期间步数 %.0f → 活动量判定 %@", steps, delta.preActivity.rawValue)
    }

    // MARK: - 模拟器演示

    /// 模拟器里没有手表数据，先写一条合成样本再读，让整条链路跑起来。
    func seedThenCapture(milliseconds: Double, isBefore: Bool) async {
        do {
            _ = try await health.seedSyntheticSDNN(milliseconds: milliseconds)
            await capture(isBefore: isBefore)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func reset() {
        before = nil; after = nil; result = nil
        subjectiveDelta = 0
        stage = .readyForBefore
        statusMessage = ""
        errorMessage = nil
    }
}
