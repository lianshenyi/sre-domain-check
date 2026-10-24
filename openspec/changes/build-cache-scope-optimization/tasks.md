## 1. 依赖与基础镜像（关联 spec 3、PRD FR-8）

- [x] 1.1 生成并提交兼容 Python 3.7 的、含哈希的生产依赖 lock，并提供离线可调用的校验脚本。
- [x] 1.2 修改 Python base Dockerfile，以 `--require-hashes` 安装 lock，并增加 pip BuildKit cache。
- [x] 1.3 修改三个 Python 角色与 Compose，显式通过 digest base tag 复用同一基础镜像。

## 2. 范围构建与发布（关联 spec 3、PRD FR-8 / NFR-5）

- [x] 2.1 新增可测试的范围/依赖摘要辅助脚本，支持 frontend、backend、deps、all 与 Git 变更检测。
- [x] 2.2 更新构建脚本，按目标确保 base、构建服务并输出耗时和 cache 证据。
- [x] 2.3 新增范围部署与回滚脚本，仅替换受影响 Compose 服务并创建镜像快照。
- [x] 2.4 为 npm Dockerfile 增加 BuildKit cache，且不改变最终镜像内容。

## 3. 验证与运维文档（关联 spec 9-11、PRD AC-1 至 AC-4、AC-9）

- [x] 3.1 编写脚本测试，覆盖依赖摘要、范围映射、构建命令选择与参数校验。
- [x] 3.2 更新 README、CLAUDE、spec、tasks 及中文变更记录，说明迁移、回滚、cold/hot benchmark 与健康检查。
- [x] 3.3 在目标机运行 cold/hot 分阶段构建、范围部署及 6 容器/入口/API/登录健康验证，保存证据。
- [x] 3.4 修复 BUG-006：frontend 范围构建必须在明确超时内完成并输出成功证据，且不得选择 Python 服务；验证连续热构建复用缓存。
