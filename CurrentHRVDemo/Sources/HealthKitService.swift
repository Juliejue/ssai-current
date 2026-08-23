import Foundation
import HealthKit

/// 一条 SDNN 读数。刻意做成 Sendable 值类型：
/// HKQuantitySample 是 class 且非 Sendable，在 Swift 6 严格并发下
/// 不能跨 continuation 边界传递，所以在查询回调里就地取值。
struct SDNNReading: Sendable, Equatable {
    let milliseconds: Double
    let endDate: Date
    /// 由本 App 自己写入的合成样本（模拟器演示用），真机统计时要剔除
    let isSynthetic: Bool
}

@MainActor
final class HealthKitService: ObservableObject {

    enum Failure: LocalizedError {
        case notAvailable
        case noSample

        var errorDescription: String? {
            switch self {
            case .notAvailable: "此设备不支持 HealthKit"
            // 注意：读权限被拒绝时返回的也是空结果，和「真的没数据」无法区分。
            // 见 README「读权限是不可见的」。
            case .noSample: "这个时间窗里没读到 HRV 样本"
            }
        }
    }

    static let sdnnType = HKQuantityType(.heartRateVariabilitySDNN)
    static let heartRateType = HKQuantityType(.heartRate)
    static let stepType = HKQuantityType(.stepCount)

    private let store = HKHealthStore()

    /// 模拟器演示开关。真机采集时置为 false，此时不申请任何写权限。
    var allowsSyntheticSamples = true

    var isAvailable: Bool { HKHealthStore.isHealthDataAvailable() }

    func requestAuthorization() async throws {
        guard isAvailable else { throw Failure.notAvailable }
        let read: Set<HKObjectType> = [Self.sdnnType, Self.heartRateType, Self.stepType]
        let share: Set<HKSampleType> = allowsSyntheticSamples ? [Self.sdnnType] : []
        try await store.requestAuthorization(toShare: share, read: read)
        // 这里不做 authorizationStatus 检查：它只反映写权限，
        // Apple 故意隐藏读权限状态，查了也没有意义。
    }

    /// 取窗口内最近一条 SDNN。
    func latestSDNN(from start: Date, to end: Date) async throws -> SDNNReading {
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)
        let sort = [NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)]
        let ownSource = HKSource.default()

        let reading: SDNNReading? = try await withCheckedThrowingContinuation { cont in
            let query = HKSampleQuery(sampleType: Self.sdnnType,
                                      predicate: predicate,
                                      limit: 1,
                                      sortDescriptors: sort) { _, samples, error in
                if let error {
                    cont.resume(throwing: error)
                    return
                }
                guard let sample = samples?.first as? HKQuantitySample else {
                    cont.resume(returning: nil)
                    return
                }
                cont.resume(returning: SDNNReading(
                    milliseconds: sample.quantity.doubleValue(for: .secondUnit(with: .milli)),
                    endDate: sample.endDate,
                    isSynthetic: sample.sourceRevision.source == ownSource
                ))
            }
            store.execute(query)
        }

        guard let reading else { throw Failure.noSample }
        return reading
    }

    /// 到访前的步数，用来识别「刚走完路」这种会系统性压低 HRV 的情况。
    func stepCount(from start: Date, to end: Date) async -> Double {
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)
        return await withCheckedContinuation { cont in
            let query = HKStatisticsQuery(quantityType: Self.stepType,
                                          quantitySamplePredicate: predicate,
                                          options: .cumulativeSum) { _, statistics, _ in
                // 步数只是协变量，读不到就按 0 处理，不阻断主流程
                cont.resume(returning: statistics?.sumQuantity()?.doubleValue(for: .count()) ?? 0)
            }
            store.execute(query)
        }
    }

    /// 过去 14 天的 SDNN 中位数，作为个人基线。只留在本地，不上传。
    func personalBaseline(days: Int = 14) async throws -> Double? {
        let end = Date()
        guard let start = Calendar.current.date(byAdding: .day, value: -days, to: end) else { return nil }
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: .strictStartDate)

        let values: [Double] = try await withCheckedThrowingContinuation { cont in
            let query = HKSampleQuery(sampleType: Self.sdnnType,
                                      predicate: predicate,
                                      limit: HKObjectQueryNoLimit,
                                      sortDescriptors: nil) { _, samples, error in
                if let error {
                    cont.resume(throwing: error)
                    return
                }
                let ms = (samples as? [HKQuantitySample] ?? [])
                    .map { $0.quantity.doubleValue(for: .secondUnit(with: .milli)) }
                cont.resume(returning: ms)
            }
            store.execute(query)
        }

        guard !values.isEmpty else { return nil }
        let sorted = values.sorted()
        let mid = sorted.count / 2
        return sorted.count.isMultiple(of: 2) ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid]
    }

    /// 模拟器演示用：写入一条合成 SDNN。手表的一条样本大约覆盖 60 秒窗口。
    @discardableResult
    func seedSyntheticSDNN(milliseconds: Double, endingAt date: Date = Date()) async throws -> SDNNReading {
        guard allowsSyntheticSamples else { throw Failure.notAvailable }
        let sample = HKQuantitySample(
            type: Self.sdnnType,
            quantity: HKQuantity(unit: .secondUnit(with: .milli), doubleValue: milliseconds),
            start: date.addingTimeInterval(-60),
            end: date
        )
        try await store.save(sample)
        return SDNNReading(milliseconds: milliseconds, endDate: date, isSynthetic: true)
    }
}
