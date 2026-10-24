# QA 测试报告：VIDE-31

**结论：PASS（P1/P2 与构建缓存范围优化已复验通过；AC-8 未验证）**

测试目标：`http://10.0.10.236:18082/`  
测试时间：2026-10-19（Asia/Singapore）  
部署版本：`209dde0df62c604de23e1c6643f43e10aab9ebc1`

## 1. 结论摘要

- 已执行：部署入口、管理员认证、受保护 API、空库列表页、表单必填校验、桌面和移动端页面巡检。
- 验收项：AC-1～AC-7 与 AC-9 有可用证据；AC-8（备份恢复演练）本轮未执行，不能判通过。
- 发现：2 项缺陷（P1 1 项、P2 1 项）。其中 P1 为首次空库部署的并发建表竞态，P2 为移动端页面横向溢出导致主要内容不可见。
- 已验证功能：`/`、`/api/getSystemVersion`、管理员登录、带 `X-Token` 的用户资料及域名/网站/证书/主机/DNS 列表请求均返回业务成功响应；无浏览器 JavaScript 异常。

## 1.1 修复复验（2026-10-19）

**复验结论：FAIL。**

| 项目 | 结果 | 独立复验结果 |
| --- | --- | --- |
| P1 首次空库并发建表 | PASS | 目标机当前 6 个容器运行、MySQL/Redis healthy；复查 backend/worker/scheduler 近 20 分钟日志中 `Duplicate key name`、`Worker failed to boot`、`Traceback` 均为 0。结合修复方空库 `docker compose up -d --build` 的实际记录与单测 `1 passed`，关闭 P1。 |
| P2 页面级横向裁切 | 部分通过 | 在 375×812 下页面宽度已从 1200px 降至 375px，`scrollWidth == innerWidth`，水平滚动消失；1440×900 桌面端亦无横向溢出。 |
| P2 移动端可用布局 | FAIL | 375px 截图中 150px 固定侧栏占据 40% 视口，内容区约 225px；“全部更新/补全ICP/域名检查/导入/导出/表格设置”等文字被压成逐字竖排，表格主内容无法有效阅读。仍属响应式布局缺陷。证据：`artifacts/screenshots/retest-domain-list-mobile.png`。 |
| 核心回归 | PASS | `GET /`、`GET /api/getSystemVersion`、管理员登录、`getUserInfo`/`getDomainInfoList`/`getMonitorList`/`getCertificateList` 均返回 HTTP 200、业务 `code=0`。 |
| AC-8 | 未验证 | 未执行备份恢复演练。 |

### DEF-003｜P2｜P2 修复后移动端工具栏与内容区仍不可用

- 责任侧：frontend / 移动端响应式布局
- 复现步骤：登录后打开 `/#/domain/list`，设置视口为 375×812。
- 期望：操作工具栏可正常阅读，列表内容保有可用宽度；侧栏在小屏幕应折叠、抽屉化或让主区获得足够空间。
- 实际：页面虽无横向滚动，但 150px 侧栏挤压主区，多个工具栏链接逐字换行，表格信息不可有效查看。
- 影响范围：375px 手机端域名监控页的搜索、批量操作和列表阅读。
- 证据：`artifacts/screenshots/retest-domain-list-mobile.png`。

## 1.2 最终 P2 复验（2026-10-22）

**最终 P2 结论：PASS。** 本次复验的线上前端版本为 `565d0484918bf990008c396c614aa032758a855e`。

| 验证项 | 结果 | 实测证据 |
| --- | --- | --- |
| 375×812 页面宽度 | PASS | `document.documentElement.scrollWidth=375`、`innerWidth=375`，无页面级横向溢出。 |
| 375×812 侧栏抽屉 | PASS | “切换导航菜单”可打开抽屉，“关闭导航菜单”可关闭；抽屉覆盖主内容而不挤压内容区。 |
| 375×812 核心操作 | PASS | 添加按钮、搜索框、状态筛选、全部更新/补全ICP/域名检查/导入/导出/表格设置完整可见可操作；搜索输入后可读回输入值。 |
| 375×812 列表和添加表单 | PASS | 列表在内容区正常显示；点击“添加”成功打开“添加域名”弹窗，关键字段及取消/确定按钮可达。 |
| 1440×900 桌面回归 | PASS | 桌面侧栏、域名列表工具栏、表格列、分页和空态正常；`scrollWidth=1440`、`innerWidth=1440`。 |
| 控制台错误 | PASS | 复验会话未见 JavaScript error；仅保留正常业务日志。 |
| 入口与登录 | PASS | `GET /` 返回 HTTP 200；管理员登录返回业务 `code=0`（凭据与 token 未记录）。 |

最终证据：

- 移动端主界面：`artifacts/screenshots/final-p2-mobile-reload.png`
- 移动端抽屉：`artifacts/screenshots/final-p2-mobile-drawer.png`
- 移动端添加弹窗：`artifacts/screenshots/final-p2-mobile-add.png`
- 桌面端回归：`artifacts/screenshots/final-p2-desktop.png`

DEF-002 和 DEF-003 均已关闭。AC-8 备份恢复不在本次安全测试条件内，状态保持“未验证”，不将其推断为通过或失败。

## 1.3 构建缓存与范围构建验收（2026-10-23）

**初始结论：FAIL（前端范围构建曾被人工在 Vite 编译阶段提前中止）。** 该记录已由 1.4 的完整 BUG-006 复验取代；此前 P1/P2 功能复验结论不变。

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| 生产依赖锁 | PASS | `scripts/check-production-lock.sh` 与 `tests/scripts/test_build_lib.sh` 本地通过；目标机 lock SHA-256 为 `dcb7d8c888558c95…`，与 `domain-admin-base:deps-dcb7d8c888558c95` 一致。 |
| 可复现安装/Gunicorn | PASS（日志复核 + 运行实测） | cold 日志记录 `pip install --require-hashes` 成功安装 `gunicorn-22.0.0` 与 `python-dateutil-2.9.0.post0`；目标机 backend 执行 `gunicorn --version` 返回 22.0.0。 |
| immutable base 与 Python 角色复用 | PASS | backend/worker/scheduler 构建均解析 `domain-admin-base:deps-dcb7d8c888558c95@sha256:5a789…`；Dockerfile 和 Compose 均使用相同 `BASE_IMAGE` 参数。 |
| cold/hot base 行为 | PASS（日志复核） | `20261023-112923-deps.log` 为 base miss、1016 秒、4 hits；`20261023-114655-deps.log` 为同 digest base hit、36 秒、2 hits。 |
| backend 范围构建 | PASS（独立实测） | 在目标机执行 `scripts/build-images.sh backend`：base hit，仅构建 backend/worker/scheduler，39 秒、2 hits；未部署或重启容器。 |
| frontend 范围构建 | 见 1.4（最终 PASS） | 初次运行在 Vite 编译阶段被人工提前中止，不能作为构建失败证据；完整复验结果见 1.4。 |
| 运行健康回归 | PASS | 6 个 Compose 容器均 running，MySQL/Redis healthy；`GET /`、版本、管理员登录、携 token 的 user/domain/monitor/certificate API 均 HTTP 200、业务 `code=0`。 |

未验证项：未重新执行冷缓存构建（会重复约 17 分钟的依赖构建，改以可复查的目标机发布日志验收）；未运行 `release-compose.sh` 部署本轮仅用于验收的范围构建镜像；AC-8 仍未验证。

## 1.4 BUG-006 前端独立范围构建复验（2026-10-23）

**最终结论：PASS。** 初次前端构建在 Vite 编译尚未完成时被人工终止；本次以脚本默认 `BUILD_TIMEOUT_SECONDS=600` 让构建完整结束，修正该误判。

| 验证项 | 结果 | 独立实测证据 |
| --- | --- | --- |
| 连续热构建 | PASS | 在目标机 `/opt/sre-domain-check` 连续执行两次 `./scripts/build-images.sh frontend`，分别在 21 秒、22 秒返回 `result=success`。 |
| 仅前端范围 | PASS | 两份日志 `20261023-121332-frontend.log`、`20261023-121353-frontend.log` 均记录 `phase=services services=frontend progress=plain timeout_seconds=600`；未选择 backend、worker、scheduler。 |
| 缓存命中 | PASS | 两次均记录 `phase=base cache=hit image-exists` 与 `cache_hits=9`；npm、Vite、最终 COPY 层均为 `CACHED`。 |
| 运行容器不受影响 | PASS | 构建前后 6 个容器 ID 完全一致：backend `3722ed5ef3ba`、frontend `9ff2fb4e65b4`、worker `17aa15259808`、scheduler `92ef2e728ccc`、MySQL `d580678ec1bb`、Redis `7036e5106366`；均为 running，MySQL/Redis healthy。 |
| 入口健康 | PASS | 构建后目标机 `GET /` 返回 HTTP 200。 |
| 脚本回归 | PASS | 本地 `bash -n scripts/build-images.sh`、`bash tests/scripts/test_build_lib.sh`、`scripts/check-production-lock.sh`、`git diff --check` 均通过。 |

未验证项：未独立执行 `BUILD_TIMEOUT_SECONDS=1` 的故障注入（已复核修复方证据，但本轮聚焦正常范围构建）；未重新执行冷缓存构建；AC-8 继续为未验证。

## 2. 验收标准对照

| 验收项 | 结果 | 实测/证据 |
| --- | --- | --- |
| AC-1 服务状态 | PASS（部署记录） | 部署方记录 6 个容器运行，MySQL、Redis healthy。 |
| AC-2 页面访问 | PASS | `GET /`：HTTP 200、`text/html`，耗时 1.13s。 |
| AC-3 API 可用 | PASS | `GET /api/getSystemVersion`：HTTP 200，`{"code":0,"data":{"version":"1.6.75"...}}`，耗时 1.10s。 |
| AC-4 登录可用 | PASS | 使用目标机受控配置中的管理员账户获取 token；仅记录结果：`code=0`、token 长度 121，不记录凭据或 token。 |
| AC-5 数据持久化 | PASS（部署记录） | 部署方已执行 `docker compose down` / `up -d --no-build` 后重新登录。 |
| AC-6 端口暴露 | PASS（部署记录） | frontend 仅发布 `18082:80`；Compose 的 MySQL、Redis 无端口映射。 |
| AC-7 角色正确 | PASS（部署记录） | backend/worker 的调度为 false/none，scheduler 为 true/worker；无调度重复启动日志。 |
| AC-8 备份恢复 | 未验证 | 本轮未进行破坏性恢复演练，也未获得演练证据。 |
| AC-9 文档合规 | PASS（抽样） | README 含 PRD/spec/tasks/部署文档索引；本报告和抽检文档未含真实凭据。 |

## 3. 缺陷明细

### DEF-001｜P1｜首次空库部署存在并发建表竞态

- 责任侧：backend / worker / scheduler 启动与数据库初始化
- 影响范围：全新服务器或清空数据目录后的首次部署；违反“按 `docker compose up -d` 可首次启动”的交付目标，部署需人工调整启动顺序。
- 复现步骤：
  1. 使用全新 MySQL 数据目录，按文档先构建基础镜像。
  2. 直接执行 `docker compose up -d --build`，让 backend、worker、scheduler 在依赖健康后并发启动。
  3. 查看三个业务容器日志。
- 期望：只有一个组件负责 schema 初始化，其他组件等待，且不出现重复索引/建表错误。
- 实际：部署方在当前版本首次空库初始化时真实遇到并发建表产生的重复索引错误；需先启动 backend 完成初始化，再启动 worker/scheduler 才能完成部署。
- 证据：部署工程师在本工单的 2026-10-19 部署回报；当前已初始化环境可用，故未在目标机清库复现，以免破坏测试环境。
- 可疑位置：三个业务容器共享的应用启动初始化逻辑及 Compose 启动门控。

### DEF-002｜P2｜移动端域名列表固定为 1200px，核心内容被横向裁切

- 责任侧：frontend / 响应式布局
- 影响范围：375px 宽手机访问 `/domain/list`；域名列表、添加、搜索、表格及分页无法在初始视口内正常使用，必须横向滚动。
- 复现步骤：
  1. 以管理员登录 `http://10.0.10.236:18082/#/domain/list`。
  2. 将浏览器视口设为 375×812。
  3. 观察初始视口并读取页面宽度。
- 期望：主要操作及内容在移动视口中可达；不出现意外横向页面滚动。
- 实际：页面 `document.documentElement.scrollWidth=1200`、`innerWidth=375`，存在横向溢出；截图中仅左侧菜单和被裁切的内容边缘可见。
- 证据：`artifacts/screenshots/issue-001-mobile-overflow.png`（本工单附件）；相同会话中两次截图均可复现。
- 可疑位置：全局 layout/sidebar 及列表页的固定最小宽度/表格容器样式。

## 4. 页面检查记录

| 页面 | 视口 | 结果 | 证据 |
| --- | --- | --- | --- |
| 登录页 `/#/login` | 1440×900 | PASS；表单正常展示 | `artifacts/screenshots/login-desktop.png` |
| 控制台 `/#/dashboard` | 1440×900 | PASS；空态统计正常，无 JS error | `artifacts/screenshots/dashboard-authenticated-desktop.png` |
| 控制台 `/#/dashboard` | 375×812 | FAIL；全局横向溢出，内容被裁切 | `artifacts/screenshots/dashboard-mobile.png` |
| 域名列表 `/#/domain/list` | 1440×900 | PASS；空态、分页与操作入口正常 | `artifacts/screenshots/domain-list-desktop.png` |
| 域名列表 `/#/domain/list` | 375×812 | FAIL；DEF-002 | `artifacts/screenshots/issue-001-mobile-overflow.png` |
| 网站列表 `/#/monitor/list` | 1440×900 | PASS；空态和添加弹窗可打开 | `artifacts/screenshots/monitor-list-desktop.png`、`artifacts/screenshots/monitor-add-form.png` |
| 证书列表 `/#/cert/list` | 1440×900 | PASS；空态正常 | `artifacts/screenshots/cert-list-desktop.png` |

## 5. API 与表单验证

- 未登录访问 `POST /api/getUserInfo`：HTTP 200、业务 `code=-1`、`msg=user_id`，未泄露资料。
- 畸形 token：HTTP 200、业务 `code=-1`、`msg=token无效`。
- 缺失用户名的登录请求：HTTP 200、业务 `code=-1`、`msg=参数缺失'username'`；空用户名/密码被拒绝。
- 已认证的 `getUserInfo`、`getDomainInfoList`、`getMonitorList`、`getCertificateList`、`getHostList`、`getDnsList`：均为 HTTP 200、业务 `code=0`。空库列表均返回规范的 `list`/`total` 结构。
- 网站监控“添加”弹窗在必填字段为空时阻止提交；未创建或修改任何业务数据。

## 6. 环境与复跑方式

```bash
# 无鉴权冒烟
curl -i http://10.0.10.236:18082/
curl -i http://10.0.10.236:18082/api/getSystemVersion

# 移动端复现 DEF-002
# 使用浏览器访问：
# http://10.0.10.236:18082/#/domain/list
# 登录后设置视口为 375×812，检查 document.documentElement.scrollWidth > innerWidth。
```

未执行的高风险范围：真实域名 WHOIS/SSL 探测、ACME 签发、远程 SSH/CDN/OSS 部署、通知渠道发送、备份恢复；这些操作会触发外部系统或改变目标数据，未获额外授权。
