import SwiftUI

struct ContentView: View {
    @StateObject private var session = VisitSession()

    /// 模拟器上没有手表数据，打开这个开关用合成样本跑通链路。
    @State private var demoMode = true

    var body: some View {
        NavigationStack {
            Form {
                if let error = session.errorMessage {
                    Section {
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(.red)
                    }
                }

                switch session.stage {
                case .needsAuthorization:
                    authorizationSection
                case .readyForBefore:
                    spaceSection
                    beforeSection
                case .atSpace:
                    beforeSection
                    afterSection
                case .done:
                    resultSection
                }

                if !session.statusMessage.isEmpty {
                    Section {
                        Text(session.statusMessage)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }

                Section {
                    Toggle("模拟器演示模式（写入合成样本）", isOn: $demoMode)
                        .onChange(of: demoMode) { _, newValue in
                            session.health.allowsSyntheticSamples = newValue
                        }
                } footer: {
                    Text("真机采集时关掉。合成样本由本 App 写入，统计时按 isSynthetic 剔除。")
                }
            }
            .navigationTitle("此在 · HRV Δ")
        }
    }

    private var authorizationSection: some View {
        Section {
            Button("申请读取 HRV 权限") {
                Task { await session.authorize() }
            }
        } footer: {
            Text("读权限的授予状态 Apple 不对外暴露，被拒绝时表现为「读不到数据」，不是报错。")
        }
    }

    private var spaceSection: some View {
        Section("空间") {
            TextField("空间 ID", text: $session.spaceID)
                .textInputAutocapitalization(.never)
        }
    }

    private var beforeSection: some View {
        Section("① 到访前") {
            if let before = session.before {
                LabeledContent("SDNN", value: String(format: "%.1f ms", before.milliseconds))
                LabeledContent("采样时间", value: before.endDate.formatted(date: .omitted, time: .standard))
                if before.isSynthetic {
                    Text("合成样本").font(.caption).foregroundStyle(.orange)
                }
            } else {
                Text("在手表上做 1 分钟正念呼吸，然后点下面读取。")
                    .font(.footnote).foregroundStyle(.secondary)
                Button("读取最近一条 HRV") {
                    Task { await session.captureBefore() }
                }
                if demoMode {
                    Button("演示：写入 42 ms 再读取") {
                        Task { await session.seedThenCapture(milliseconds: 42, isBefore: true) }
                    }
                    .foregroundStyle(.orange)
                }
            }
        }
    }

    private var afterSection: some View {
        Section("② 到访后") {
            Text("到店后先静坐 3–5 分钟，再做第二次呼吸——刚走完路会压低 HRV。")
                .font(.footnote).foregroundStyle(.secondary)

            Picker("主观变化", selection: $session.subjectiveDelta) {
                Text("差很多").tag(-2)
                Text("差一点").tag(-1)
                Text("没变化").tag(0)
                Text("好一点").tag(1)
                Text("好很多").tag(2)
            }

            Button("读取最近一条 HRV") {
                Task { await session.captureAfter() }
            }
            if demoMode {
                Button("演示：写入 58 ms 再读取") {
                    Task { await session.seedThenCapture(milliseconds: 58, isBefore: false) }
                }
                .foregroundStyle(.orange)
            }
        }
    }

    @ViewBuilder
    private var resultSection: some View {
        if let result = session.result {
            Section("结果") {
                LabeledContent("ln Δ", value: String(format: "%+.4f", result.lnDelta))
                LabeledContent("相对变化", value: String(format: "%+.1f%%", result.percentChange))
                LabeledContent("活动量", value: result.preActivity.rawValue)
                LabeledContent("置信度", value: result.confidence.rawValue)
                LabeledContent("主观", value: "\(result.subjectiveDelta)")
            } footer: {
                Text("单次 Δ 的测量噪声大于多数空间的真实效应，只能作为个人日记里的弱信号；"
                     + "要跨用户聚合几十次以上，才能说「在这里的人普遍…」。")
            }

            Section("将要上传的字段") {
                Text(uploadJSON(result))
                    .font(.system(.caption, design: .monospaced))
            } footer: {
                Text("没有姓名、没有原始心率流、没有 before/after 绝对值、没有个人基线。")
            }

            Section {
                Button("再来一次") { session.reset() }
            }
        }
    }

    private func uploadJSON(_ delta: VisitDelta) -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        guard let data = try? encoder.encode(delta.uploadPayload),
              let text = String(data: data, encoding: .utf8) else { return "—" }
        return text
    }
}

#Preview {
    ContentView()
}
