# quantstrategylab.github.io

[English](README.md) | 简体中文

QuantStrategyLab 的静态组织官网仓库，通过 GitHub Pages 发布 `site/` 目录。

## 状态

维护中。本仓库发布静态组织主页与图标资源，仅用于项目信息展示，不构成任何金融或投资建议，也不执行交易或连接任何券商接口。

## 简介

本仓库包含介绍 QuantStrategyLab 及其开源项目的纯 HTML/CSS 落地页，以及用于生成和校验 `site/` 目录的图标源文件、规格定义与本地验证脚本。

## 不适用范围

本仓库不包含交易策略、行情数据管道、执行引擎或用户账号系统，也没有后端服务、服务端渲染或第三方运行时依赖。

## 快速开始

环境要求：Node.js 20+ 与 Python 3.12+。

```bash
# 重新生成站点图标并运行 Node 测试套件
npm test

# 运行 Python 站点检查单元测试与发布检查
python3 -m unittest discover -s scripts -p "test_*.py"
python3 scripts/check_site.py --phase 2
```

如需在本地预览静态站点，可使用任意静态 HTTP 服务器托管 `site/` 目录：

```bash
python3 -m http.server --directory site 8080
```

## 配置

本站点不需要运行时环境变量或配置文件。GitHub Pages 部署配置位于 `.github/workflows/pages.yml`，仅上传并发布 `site/` 目录。

| 配置项 | 必填 | 默认值 | 用途 |
|---|---|---|---|
| `site/` | 是 | 仓库内 `site/` | 上传至 GitHub Pages 的静态 HTML、CSS、图标与 manifest |
| 本地预览端口 | 否 | `8080` | 本地预览 `site/` 时使用的 HTTP 端口 |

## 架构

已发布站点为 `site/` 目录下的纯静态 HTML 与 CSS，运行时不发起任何外部网络请求。图标源文件与规格保存在 `site/` 之外的 `site-icons/` 目录中，由 `scripts/build-site-icons.mjs` 生成并同步到 `site/`。发布检查会在部署前校验图标完整性、对比度、双语键值一致性及公开内容边界。

## 仓库结构

```text
site/           实际发布的静态站点（index.html、assets/、图标与 manifest）
site-icons/     图标源文件、对比度测量数据与规格说明
scripts/        图标构建脚本（build-site-icons.mjs）与站点检查脚本
tests/          覆盖图标与落地页不变量的 Node 测试套件
.github/        GitHub Actions 工作流、CODEOWNERS 与 Dependabot 配置
```

## 参与贡献

贡献流程、提交规范与公开内容边界请参见 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [AGENTS.md](AGENTS.md)。

## 安全

安全漏洞披露方式请参见 [SECURITY.md](SECURITY.md)，请勿在公开 issue 中提交漏洞细节。

## 许可证

基于 [MIT License](LICENSE) 发布。
