import Foundation

/// 到访前 20 分钟的活动量。
/// 走路到店会激活交感神经、压低「到访后」的 HRV——这是整套测量里
/// 方向性最强的偏差源：不修正的话，所有需要走路到达的空间都会被打成负面。
enum ActivityLevel: String, Codable, Sendable {
    case rest, walk, exercise

    static func from(steps: Double) -> ActivityLevel {
        switch steps {
        case ..<200: .rest
        case ..<1500: .walk
        default: .exercise
        }
    }
}

enum Confidence: String, Codable, Sendable { case high, low }

/// 一次到访的完整记录（本地）。
struct VisitDelta: Identifiable, Sendable {
    let id = UUID()
    let spaceID: String
    let windowStart: Date
    let windowEnd: Date

    /// ln(after) − ln(before)。HRV 分布右偏且个体差异从 20ms 到 150ms，
    /// 绝对差值不能跨人比较，取对数差才可以。
    let lnDelta: Double

    let preActivity: ActivityLevel
    let confidence: Confidence
    /// −2…+2 主观量表。生理信号只有和主观评分交叉验证才有说服力，且是 HRV 读不到时的兜底。
    let subjectiveDelta: Int

    /// 个人基线，仅用于本地展示，不进上传体。
    let localBaselineSDNN: Double?

    var percentChange: Double { expm1(lnDelta) * 100 }

    /// 真正离开设备的字段，严格对齐「只存 Δ、空间 ID、时间段」。
    /// 没有姓名、没有原始心率流、没有 before/after 的绝对值、没有基线。
    var uploadPayload: VisitDeltaUpload {
        VisitDeltaUpload(spaceID: spaceID,
                         windowStart: windowStart,
                         windowEnd: windowEnd,
                         lnDelta: lnDelta,
                         preActivity: preActivity,
                         confidence: confidence,
                         subjectiveDelta: subjectiveDelta)
    }

    static func make(spaceID: String,
                     before: SDNNReading,
                     after: SDNNReading,
                     preActivity: ActivityLevel,
                     subjectiveDelta: Int,
                     baseline: Double?) -> VisitDelta {
        let gap = after.endDate.timeIntervalSince(before.endDate)
        // 间隔太短说明还没坐下来，太长说明中间发生了别的事；剧烈活动直接降级。
        let confidence: Confidence =
            (gap >= 600 && gap <= 4 * 3600 && preActivity != .exercise) ? .high : .low

        return VisitDelta(
            spaceID: spaceID,
            windowStart: before.endDate,
            windowEnd: after.endDate,
            lnDelta: log(after.milliseconds) - log(before.milliseconds),
            preActivity: preActivity,
            confidence: confidence,
            subjectiveDelta: subjectiveDelta,
            localBaselineSDNN: baseline
        )
    }
}

struct VisitDeltaUpload: Codable, Sendable {
    let spaceID: String
    let windowStart: Date
    let windowEnd: Date
    let lnDelta: Double
    let preActivity: ActivityLevel
    let confidence: Confidence
    let subjectiveDelta: Int
}
