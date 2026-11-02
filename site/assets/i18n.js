/* QuantStrategyLab organisation landing — locale dictionary.
   English and zh-CN key sets must stay identical; tests/landing.test.mjs enforces parity. */
(function (root, factory) {
  "use strict";
  var dictionary = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = dictionary;
  }
  root.QSL_I18N = dictionary;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  return {
    en: {
      doc_title: "QuantStrategyLab — Systematic strategies, evidence first",
      meta_description:
        "QuantStrategyLab is an independent research group building and testing systematic investment strategies under explicit risk controls. Research only; not investment advice.",

      nav_label: "Primary",
      lang_switch: "Switch language",
      theme_to_dark: "Switch to dark theme",
      theme_to_light: "Switch to light theme",
      menu: "Menu",
      menu_close: "Close menu",

      n1: "Systems",
      n2: "Principles",
      n3: "Publications",
      n4: "GitHub",

      h_eye: "Quantitative research · Trading systems",
      h_title:
        "Systematic strategies, decided on evidence and run under <em>explicit controls</em>.",
      h_lede:
        "QuantStrategyLab is an independent research group. We build and test systematic investment strategies, the baselines they must beat, and the risk, paper-trading and reconciliation systems that keep them honest.",
      h_cta1: "Read the research",
      h_cta2: "How we work",

      c_title: "Lifecycle of a strategy",
      c_tag: "Gated",
      c1: "Offline evaluation",
      c1p: "Frozen inputs, a fixed calendar and versioned metrics, compared with index baselines.",
      c1g: "→ adopt · reject · insufficient evidence",
      c2: "Paper sessions",
      c2p: "Simulated orders over complete exchange trading sessions, with readable receipts.",
      c2g: "→ min. 3 sessions, 5 recommended",
      c3: "Risk and reconciliation",
      c3p: "Current facts checked against broker records; stale or missing data fails closed.",
      c3g: "→ unreconciled stays unreconciled",
      c4: "Owner decision",
      c4p: "Account, amount and scope are confirmed once by a person. Nothing activates by default.",
      c4g: "→ explicit, one-time, revocable",
      c_foot:
        "A stage that lacks evidence does not pass. Missing, stale and unknown are recorded as such.",

      s_eye: "What we build",
      s_title: "Six systems, one standard of evidence.",
      s_lede:
        "Each system has a single owner and a written contract. Status is shown as observed, never inferred from a plan or a merged change.",
      out: "Output",
      a1k: "Research",
      a1: "Strategy research",
      a1p: "Candidate-by-candidate evaluation with deflated Sharpe and overfitting checks. Where a statistic cannot be computed, it is reported as uncomputable rather than estimated.",
      a1o: "Adopt / reject / insufficient-evidence decisions",
      a2k: "Baselines",
      a2: "Index baselines",
      a2p: "Buy-and-hold references for the Nasdaq-100 and the S&P 500, with plain and moving-average-adjusted DCA bounded between 0.5× and 2×. Reporting benchmarks stay lump-sum.",
      a2o: "The bar every strategy must clear",
      a3k: "Risk",
      a3: "Risk controls",
      a3p: "Current unsafe facts override projected healthy ones. Stale inputs, transport errors and unknown states block an action instead of being counted as warnings.",
      a3o: "Fail-closed pre-trade checks",
      a4k: "Paper",
      a4: "Paper trading",
      a4p: "Strategies run against live market sessions without capital. Only complete, readable sessions count towards the gate; partial days do not.",
      a4o: "Session receipts for review",
      a5k: "Ledger",
      a5: "Forward reconciliation",
      a5p: "Positions, cash and executions are reconciled forward from a fixed start date. There is no backfill and no invented opening balance.",
      a5o: "A public observation ledger",
      a6k: "Tooling",
      a6: "Research infrastructure",
      a6p: "A gateway for model-assisted research jobs with per-caller quotas, plus redacted notifications. Unconfigured values show as unknown, not as zero.",
      a6o: "Auditable job and delivery records",

      p_eye: "Principles",
      p_title: "How we work.",
      p_lede: "These rules apply to every repository and every job, including automated ones.",
      p1: "Evidence before adoption",
      p1p: "A candidate is adopted only when its evidence is complete. Otherwise the decision is recorded as insufficient, not deferred into a yes.",
      p2: "Fail closed",
      p2p: "Unknown, invalid and missing inputs stop the action. No state defaults to allow.",
      p3: "Forward-only records",
      p3p: "We do not reconstruct history to make a record look complete. Gaps stay visible.",
      p4: "People decide capital",
      p4p: "Live activation, accounts, amounts and risk limits are decided by the owner, once and explicitly. Automation works within that scope.",
      p5: "Methods, not promises",
      p5p: "We publish how strategies are evaluated. We do not publish return figures or forecasts.",
      p6: "Privacy by default",
      p6p: "Account identifiers are masked everywhere: logs, reports, pages and test fixtures.",

      i_eye: "Publications",
      i_title: "Where to read more.",
      i_lede: "Every site below is generated from the same source records.",
      i1: "Research notes",
      i1p: "Strategy reviews, evaluation methods and the reasoning behind each decision.",
      i2: "Reconciliation ledger",
      i2p: "Daily forward-only observation of broker records, with unreconciled items listed.",
      i3: "Source code",
      i3p: "Libraries, contracts and tests, maintained in public repositories.",
      i4: "Gateway console",
      i4p: "Operational view of the research gateway. Sign-in required.",
      pub: "Public",
      restr: "Members only",
      no_public_link: "No public link is available.",

      f_disc:
        "QuantStrategyLab publishes research and engineering work. Nothing on this site is investment advice, an offer, or a solicitation, and we do not publish performance figures. Strategies described here may be in research, paper trading or retired.",
      f_meta: "Research only · Not investment advice"
    },
    "zh-CN": {
      doc_title: "QuantStrategyLab — 系统化策略，以证据为先",
      meta_description:
        "QuantStrategyLab 是一个独立研究团队，构建并检验系统化投资策略，并在明确的风控下运行。仅供研究，不构成投资建议。",

      nav_label: "主导航",
      lang_switch: "切换语言",
      theme_to_dark: "切换到深色主题",
      theme_to_light: "切换到浅色主题",
      menu: "菜单",
      menu_close: "关闭菜单",

      n1: "系统",
      n2: "原则",
      n3: "公开资料",
      n4: "GitHub",

      h_eye: "量化研究 · 交易系统",
      h_title: "系统化策略，以证据决策，<br>在<em>明确的控制</em>下运行。",
      h_lede:
        "QuantStrategyLab 是一个独立研究团队。我们构建并检验系统化投资策略、策略必须跑赢的基准，以及让它们保持诚实的风控、模拟交易与对账系统。",
      h_cta1: "阅读研究",
      h_cta2: "我们的工作方式",

      c_title: "一个策略的生命周期",
      c_tag: "逐级把关",
      c1: "离线评估",
      c1p: "冻结输入、固定交易日历与有版本的指标，并与指数基准对照。",
      c1g: "→ 采用 · 拒绝 · 证据不足",
      c2: "模拟交易",
      c2p: "在完整的交易所交易日内模拟下单，留下可读的回执。",
      c2g: "→ 至少 3 个交易日，建议 5 个",
      c3: "风控与对账",
      c3p: "以券商记录核对当前事实；数据过期或缺失时一律阻断。",
      c3g: "→ 未对平的始终标为未对平",
      c4: "负责人决定",
      c4p: "账户、金额与范围由人一次性确认。任何功能都不会默认启用。",
      c4g: "→ 明确、一次性、可撤销",
      c_foot: "缺少证据的环节不会通过。缺失、过期与未知都会如实记录。",

      s_eye: "我们构建什么",
      s_title: "六个系统，同一套证据标准。",
      s_lede:
        "每个系统都有唯一的负责人和书面契约。状态只按实际观察展示，不会根据计划或已合并的改动推断。",
      out: "产出",
      a1k: "研究",
      a1: "策略研究",
      a1p: "逐个候选评估，使用缩减夏普比率与过拟合检验。无法计算的统计量如实标为“不可计算”，不做估计。",
      a1o: "采用 / 拒绝 / 证据不足的决策",
      a2k: "基准",
      a2: "指数基准",
      a2p: "纳斯达克 100 与标普 500 的买入持有基准，支持普通定投和按均线偏离调整的定投（0.5×–2× 封顶）。报告基准保持一次性投入。",
      a2o: "每个策略都必须跨过的门槛",
      a3k: "风控",
      a3: "风险控制",
      a3p: "当前的不安全事实优先于预测的健康状态。过期输入、传输错误与未知状态会直接阻断操作，而不是计为警告。",
      a3o: "失败即阻断的交易前检查",
      a4k: "模拟",
      a4: "模拟交易",
      a4p: "策略在真实行情交易日中运行，但不动用资金。只有完整、可读的交易日计入门槛，不完整的交易日不算。",
      a4o: "可供审阅的交易日回执",
      a5k: "账本",
      a5: "前向对账",
      a5p: "持仓、现金与成交从固定起始日起向前对账。不回填历史，也不虚构期初余额。",
      a5o: "公开的对账观察账本",
      a6k: "工具",
      a6: "研究基础设施",
      a6p: "为模型辅助的研究任务提供网关和按调用方的配额，并发送脱敏通知。未配置的数值显示为未知，而不是 0。",
      a6o: "可审计的任务与投递记录",

      p_eye: "原则",
      p_title: "我们的工作方式。",
      p_lede: "这些规则适用于每个仓库和每个任务，包括自动化任务。",
      p1: "先有证据，再采用",
      p1p: "只有证据完整时才会采用候选策略。否则如实记为“证据不足”，不会拖延成默认同意。",
      p2: "失败即阻断",
      p2p: "未知、无效与缺失的输入都会停止操作，任何状态都不默认放行。",
      p3: "只向前记录",
      p3p: "我们不为了让记录看起来完整而重建历史。缺口始终可见。",
      p4: "资金由人决定",
      p4p: "实盘启用、账户、金额与风控参数由负责人一次性明确决定，自动化只在该范围内工作。",
      p5: "公开方法，不做承诺",
      p5p: "我们公开策略的评估方法，不公布收益数字或预测。",
      p6: "默认保护隐私",
      p6p: "账户标识在日志、报告、页面和测试数据中一律脱敏。",

      i_eye: "公开资料",
      i_title: "延伸阅读。",
      i_lede: "以下站点都由同一份源记录生成。",
      i1: "研究笔记",
      i1p: "策略评审、评估方法，以及每项决策背后的理由。",
      i2: "对账账本",
      i2p: "每日对券商记录的前向观察，并列出所有未对平项。",
      i3: "源代码",
      i3p: "库、契约与测试，维护在公开仓库中。",
      i4: "网关控制台",
      i4p: "研究网关的运行视图，需要登录。",
      pub: "公开",
      restr: "仅限成员",
      no_public_link: "暂无公开链接。",

      f_disc:
        "QuantStrategyLab 发布研究与工程成果。本站内容不构成投资建议、要约或招揽，我们也不公布业绩数据。文中描述的策略可能处于研究、模拟交易或已停用状态。",
      f_meta: "仅供研究 · 不构成投资建议"
    }
  };
});
