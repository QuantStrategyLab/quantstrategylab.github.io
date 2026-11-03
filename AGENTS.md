# AGENTS.md

## 内容边界

<!-- content-boundary:begin -->
- Public material carries no real resource names or accounts: write
  `gs://<bucket>/...` and `<account-id>`, and use synthetic values in
  examples.
- Read bucket names, accounts and hostnames from `vars.*`, the
  environment, or protected configuration; do not hard-code them in
  source, workflows or documents.
- A hash is not anonymisation: a commit id, digest or truncated
  identifier that leads back to the real object does not belong in
  public material.
- Judge a change by `git diff` and `git ls-files`; `.gitignore` only
  affects untracked files and is not evidence that nothing leaked.
<!-- content-boundary:end -->

## 项目是什么

QuantStrategyLab 官网。静态站点，没有框架、没有服务端渲染、没有构建产物目录之外的运行时。Pages 工作流只上传 `site/`，其余目录不会进入公开站点。

## 技术栈

纯 HTML/CSS，构建与测试用 Node 自带的 `node --test`。无第三方运行时依赖。

## 目录

- `site/` — 实际发布的站点：`index.html` 与 `assets/`。这是唯一会上线的目录。
- `site-icons/` — 五个产品面的图标源文件、规格与构建输入。不上线。
- `scripts/` — `build-site-icons.mjs` 生成图标，`site-icons-spec.mjs` 定义规格。
- `tests/` — `node:test` 用例，覆盖图标生成与落地页。

## 本地验证

```bash
npm test
```

`pretest` 会先跑 `build:icons`，所以这条命令同时验证图标能重新生成。改动只涉及文案时可只跑相关用例，并在 PR 里说明未跑的部分。

## 约束

- 站点是公开的：不写真实账号、内网主机名、个人子域名或部署机路径。
- 图标改动必须符合 `site-icons/spec` 的几何与对比度要求，测试会检查。
- 只有 `site/` 会被发布；不要把仅供内部查看的材料放进 `site/`。
