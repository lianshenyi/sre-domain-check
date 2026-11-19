## Why

域名列表批量刷新时需要显示处理进度，让用户看到成功项和失败项。批量任务在后台处理时，用户可以留在当前列表查看执行结果。

## What Changes

- 根据启动接口返回的任务 ID 显示批量刷新进度，终态刷新证书列表。
- 查询失败时提示并重试，页面离开时取消进度查询。

## Capabilities

### New Capabilities

### Modified Capabilities

- `domain-cert-batches` 增加域名列表进度展示和终态刷新要求。

## Impact

改动范围为证书域名列表及现有 API 客户端，复用现有接口、鉴权与 Compose 配置。
